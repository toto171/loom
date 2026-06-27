"""Runtime monitors — translate contract ``failureModes`` into live predicates
evaluated against the bus + plant ground truth each tick (HANDOFF §5.2 runtime
monitors).

A monitor is built from a failure mode's ``detect`` predicate plus the contract's
``bindings`` (variable name -> source). A monitor fires when ``detect`` evaluates
true (the failure condition holds) or when a referenced signal is unavailable
(e.g. a dropped-out sensor -> UNAVAILABLE). Failure modes whose ``detect`` uses
variables with no binding are skipped (recorded, not silently dropped).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loom.monitors.predicate import (
    UNAVAILABLE,
    PredicateError,
    evaluate,
    referenced_names,
)

if TYPE_CHECKING:
    from loom.bus.base import Bus


@dataclass
class Violation:
    t: float
    module: str
    monitor_id: str
    kind: str  # "failure_detected" | "signal_unavailable"
    message: str


@dataclass
class Monitor:
    module: str
    monitor_id: str
    detect: str
    bindings: dict[str, str]
    effect: str


def resolve_bindings(bindings: dict[str, str], bus: "Bus", truth: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve each ``variable -> source`` binding to a concrete value.

    Sources: ``signal:<VSS path>`` (bus, None if absent/dropped),
    ``truth:<key>`` (plant ground truth), ``const:<number>``.
    """
    truth = truth or {}
    out: dict[str, Any] = {}
    for var, source in bindings.items():
        scheme, _, ref = source.partition(":")
        if scheme == "signal":
            out[var] = bus.read(ref)
        elif scheme == "truth":
            out[var] = truth.get(ref)
        elif scheme == "const":
            out[var] = float(ref)
        else:
            raise PredicateError(f"unknown binding source {source!r} for variable {var!r}")
    return out


@dataclass
class MonitorEngine:
    monitors: list[Monitor] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    @classmethod
    def from_modules(cls, modules) -> "MonitorEngine":
        monitors: list[Monitor] = []
        skipped: list[dict] = []
        for m in modules:
            contract = m.contract
            bindings = getattr(contract, "bindings", {}) or {}
            for fm in contract.failure_modes:
                try:
                    names = referenced_names(fm.detect)
                except PredicateError:
                    skipped.append(
                        {"module": m.module_id, "monitor": fm.id, "reason": "malformed predicate"}
                    )
                    continue
                unbound = sorted(n for n in names if n not in bindings)
                if unbound:
                    skipped.append(
                        {"module": m.module_id, "monitor": fm.id, "unbound": unbound}
                    )
                    continue
                monitors.append(
                    Monitor(
                        module=m.module_id,
                        monitor_id=fm.id,
                        detect=fm.detect,
                        bindings={n: bindings[n] for n in names},
                        effect=fm.effect,
                    )
                )
        return cls(monitors=monitors, skipped=skipped)

    def evaluate(self, t: float, bus: "Bus", truth: dict[str, Any] | None = None) -> list[Violation]:
        fired: list[Violation] = []
        for mon in self.monitors:
            variables = resolve_bindings(mon.bindings, bus, truth)
            try:
                result = evaluate(mon.detect, variables)
            except PredicateError as exc:
                fired.append(
                    Violation(
                        t=round(float(t), 6),
                        module=mon.module,
                        monitor_id=mon.monitor_id,
                        kind="monitor_error",
                        message=f"{mon.module}/{mon.monitor_id}: monitor could not be "
                        f"evaluated ({exc})",
                    )
                )
                continue
            if result is UNAVAILABLE:
                fired.append(
                    Violation(
                        t=round(float(t), 6),
                        module=mon.module,
                        monitor_id=mon.monitor_id,
                        kind="signal_unavailable",
                        message=f"{mon.module}/{mon.monitor_id}: a required signal is "
                        f"unavailable (effect: {mon.effect})",
                    )
                )
            elif result is True:
                fired.append(
                    Violation(
                        t=round(float(t), 6),
                        module=mon.module,
                        monitor_id=mon.monitor_id,
                        kind="failure_detected",
                        message=f"{mon.module}/{mon.monitor_id}: failure condition met "
                        f"[{mon.detect}] (effect: {mon.effect})",
                    )
                )
        self.violations.extend(fired)
        return fired
