"""Static composition checker (HANDOFF §5.2).

Verifies that the composed modules are actually compatible in the dimensions that
matter — the part that makes a "default-or-swap" vehicle safe rather than merely
convenient. Modules, the plant, and the scenario stimulus are all modeled as
signal *participants* (each with provides/requires); the rules operate uniformly
over them.

Rules (v0 minimum + extensions — see "Extensions beyond §5.2" in README):
- producer_uniqueness: no VSS path is produced by more than one participant.
- signal_resolution:   every `requires` path is produced by exactly one OTHER
                       participant (self-production is a self-loop warning, not a
                       discharged dependency). An `optional` require with no
                       producer is a warning, not an error.
- unit_consistency:    units declared on both sides of a connection must agree;
                       a connection where one side declares a unit and the other
                       omits it is flagged as under-specified (warning).
- timing:              no module's deadline exceeds its period, and for each
                       declared `timing.resource` (co-location), total utilization
                       (sum of deadline/period) does not exceed 1.0.
- assume_guarantee:    an assumption that references a VSS path is discharged only
                       if ANOTHER participant produces that path (a producer-presence
                       proxy). Free-text assumptions are reported as
                       not-statically-verifiable (warning). Matching an assumption
                       against the producing module's `guarantee` predicate is not
                       implemented; runtime predicate evaluation is M3 monitors.
- license (extension): reference/default modules must carry an OSI-approved SPDX
                       license; a non-OSI license is a warning (proprietary swaps
                       are allowed but flagged).

The safety-line swap gate (HANDOFF §5.2 final bullet) is enforced at M4; safety
levels are surfaced in the report here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from loom.contracts.model import Signal

_VSS_TOKEN = re.compile(r"Vehicle(?:\.[A-Za-z0-9]+)+")

RULES = (
    "producer_uniqueness",
    "signal_resolution",
    "unit_consistency",
    "timing",
    "assume_guarantee",
    "license",
)

# SPDX identifiers of OSI-approved open-source licenses (non-exhaustive). Loom's
# reference/default modules must carry one of these; proprietary swaps may declare
# any SPDX id but are flagged so the "open defaults" property stays visible.
OSI_APPROVED_LICENSES = frozenset({
    "Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "0BSD", "ISC", "Zlib",
    "MPL-2.0", "EPL-2.0", "BSL-1.0", "Unlicense", "Artistic-2.0", "EUPL-1.2",
    "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later", "CDDL-1.0",
})


@dataclass
class Participant:
    name: str
    provides: list[Signal] = field(default_factory=list)
    requires: list[Signal] = field(default_factory=list)
    safety_level: str | None = None
    assume: list[str] = field(default_factory=list)
    guarantee: list[str] = field(default_factory=list)
    period_ms: float | None = None
    deadline_ms: float | None = None
    resource: str | None = None
    license: str | None = None
    is_module: bool = False


@dataclass
class CheckIssue:
    severity: str  # "error" | "warning"
    rule: str
    message: str
    where: str | None = None


@dataclass
class SignalEdge:
    path: str
    unit: str | None
    producers: list[str]
    consumers: list[str]


@dataclass
class CheckReport:
    vehicle: str
    participants: list[Participant]
    graph: list[SignalEdge]
    issues: list[CheckIssue]

    @property
    def errors(self) -> list[CheckIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[CheckIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _to_signals(items) -> list[Signal]:
    out: list[Signal] = []
    for it in items or []:
        if isinstance(it, Signal):
            out.append(it)
        else:
            out.append(
                Signal(
                    path=it["path"],
                    unit=it.get("unit"),
                    optional=bool(it.get("optional", False)),
                )
            )
    return out


def build_participants(modules, *, plant=None, stimulus_provides=None) -> list[Participant]:
    """Build the participant list from resolved modules + plant + scenario stimulus."""
    participants: list[Participant] = []
    for m in modules:
        c = m.contract
        participants.append(
            Participant(
                name=m.module_id,
                provides=list(c.provides),
                requires=list(c.requires),
                safety_level=c.safety_level,
                assume=list(c.assume),
                guarantee=list(c.guarantee),
                period_ms=c.period_ms,
                deadline_ms=c.deadline_ms,
                resource=c.resource,
                license=c.license,
                is_module=True,
            )
        )
    if plant is not None:
        participants.append(
            Participant(
                name="plant",
                provides=_to_signals(getattr(plant, "provides", [])),
                requires=_to_signals(getattr(plant, "requires", [])),
            )
        )
    if stimulus_provides is not None:
        participants.append(
            Participant(name="scenario", provides=_to_signals(stimulus_provides))
        )
    return participants


def check_participants(vehicle: str, participants: list[Participant]) -> CheckReport:
    issues: list[CheckIssue] = []

    producers: dict[str, list[tuple[str, str | None]]] = {}
    for p in participants:
        for s in p.provides:
            producers.setdefault(s.path, []).append((p.name, s.unit))

    consumers: dict[str, list[str]] = {}
    for p in participants:
        for s in p.requires:
            consumers.setdefault(s.path, []).append(p.name)

    # producer_uniqueness
    for path, prods in sorted(producers.items()):
        if len(prods) > 1:
            issues.append(
                CheckIssue(
                    "error",
                    "producer_uniqueness",
                    f"signal '{path}' has multiple producers: {', '.join(n for n, _ in prods)}",
                    path,
                )
            )

    # signal_resolution + unit_consistency. §5.2: a `requires` must be produced by
    # exactly one OTHER participant, so self-production doesn't discharge a dependency.
    for p in participants:
        for req in p.requires:
            prods = producers.get(req.path, [])
            external = [(n, u) for n, u in prods if n != p.name]
            if not prods:
                optional = getattr(req, "optional", False)
                issues.append(
                    CheckIssue(
                        "warning" if optional else "error",
                        "signal_resolution",
                        f"{p.name} {'optionally requires' if optional else 'requires'} "
                        f"'{req.path}' but no participant provides it",
                        req.path,
                    )
                )
                continue
            if not external:
                issues.append(
                    CheckIssue(
                        "warning",
                        "signal_resolution",
                        f"{p.name} requires '{req.path}' which only it produces "
                        f"(self-loop — cross-module wiring expected)",
                        req.path,
                    )
                )

            # unit_consistency: compare all declared units across producer(s) + consumer.
            declared = {u for _, u in prods if u is not None}
            if req.unit is not None:
                declared.add(req.unit)
            if len(declared) > 1:
                issues.append(
                    CheckIssue(
                        "error",
                        "unit_consistency",
                        f"unit mismatch on '{req.path}': conflicting units "
                        f"{sorted(declared)} declared across {p.name} and its producer(s)",
                        req.path,
                    )
                )
            elif len(declared) == 1:
                producer_units = [u for _, u in prods]
                if req.unit is None or any(u is None for u in producer_units):
                    only = next(iter(declared))
                    issues.append(
                        CheckIssue(
                            "warning",
                            "unit_consistency",
                            f"under-specified unit on '{req.path}': one side declares "
                            f"'{only}', the other omits it",
                            req.path,
                        )
                    )

    # timing: per-module deadline<=period, plus utilization per shared resource.
    # Modules without an explicit `resource` are assumed independently scheduled
    # (their own resource), so they never contend — only co-located modules can
    # overcommit. This matches a zonal/central-HPC platform with many cores.
    resource_util: dict[str, float] = {}
    for p in participants:
        if p.period_ms is None or p.deadline_ms is None:
            continue
        if p.deadline_ms > p.period_ms:
            issues.append(
                CheckIssue(
                    "error",
                    "timing",
                    f"{p.name}: deadline {p.deadline_ms:g}ms exceeds period {p.period_ms:g}ms",
                    p.name,
                )
            )
        if p.period_ms > 0 and p.resource:
            resource_util[p.resource] = resource_util.get(p.resource, 0.0) + p.deadline_ms / p.period_ms
    for resource, util in sorted(resource_util.items()):
        if util > 1.0 + 1e-9:
            issues.append(
                CheckIssue(
                    "error",
                    "timing",
                    f"timing overcommit on resource '{resource}': total compute "
                    f"utilization {util:.2f} > 1.0 (sum of deadline/period)",
                    resource,
                )
            )

    # assume_guarantee. §5.2: assumptions are "discharged by some module's guarantee
    # or the plant" — i.e. by ANOTHER participant. A path-bearing assumption is taken
    # as discharged when an external participant produces that path (a producer-presence
    # proxy; matching against the producer's guarantee predicate is left to M3 monitors).
    for p in participants:
        for assumption in p.assume:
            paths = _VSS_TOKEN.findall(assumption)
            if not paths:
                issues.append(
                    CheckIssue(
                        "warning",
                        "assume_guarantee",
                        f'{p.name}: assumption not statically verifiable (no VSS path '
                        f'referenced): "{assumption}"',
                        p.name,
                    )
                )
                continue
            for path in paths:
                external = [n for n, _ in producers.get(path, []) if n != p.name]
                if external:
                    continue
                if path in producers:  # only the asserting participant produces it
                    issues.append(
                        CheckIssue(
                            "error",
                            "assume_guarantee",
                            f"{p.name}: assumption references '{path}' which only it produces; "
                            f'assumptions must be discharged by another module or the plant: "{assumption}"',
                            path,
                        )
                    )
                else:
                    issues.append(
                        CheckIssue(
                            "error",
                            "assume_guarantee",
                            f"{p.name}: assumption references '{path}' which no participant "
                            f'provides: "{assumption}"',
                            path,
                        )
                    )

    # license: reference/default modules must be OSI-approved open source.
    for p in participants:
        if not p.is_module:
            continue
        if not p.license:
            issues.append(
                CheckIssue("error", "license", f"{p.name}: no license declared", p.name)
            )
        elif p.license not in OSI_APPROVED_LICENSES:
            issues.append(
                CheckIssue(
                    "warning",
                    "license",
                    f"{p.name}: license '{p.license}' is not a recognized OSI-approved "
                    f"open-source license (reference/default modules should be open; "
                    f"proprietary swaps are allowed but flagged)",
                    p.name,
                )
            )

    graph = []
    for path in sorted(set(producers) | set(consumers)):
        prods = producers.get(path, [])
        unit = next((u for _, u in prods if u is not None), None)
        graph.append(
            SignalEdge(
                path=path,
                unit=unit,
                producers=[n for n, _ in prods],
                consumers=sorted(consumers.get(path, [])),
            )
        )

    return CheckReport(vehicle=vehicle, participants=participants, graph=graph, issues=issues)


def check_composition(vehicle: str, modules, *, plant=None, stimulus_provides=None) -> CheckReport:
    participants = build_participants(modules, plant=plant, stimulus_provides=stimulus_provides)
    return check_participants(vehicle, participants)
