"""Toolchain dependency SBOM — the transitive Python dependency closure of the
Loom runtime, built from installed package metadata (``importlib.metadata``).

This complements the vehicle SBOM in :mod:`loom.assurance.sbom`. That one is a
**bill of the composed vehicle modules** + their declared licenses (module-level,
not a transitive scan); THIS is the **transitive dependency closure of the Loom
toolchain** — every *installed* PyPI distribution in ``loom``'s runtime closure,
with versions, licenses, and PURLs (``pkg:pypi/...``), plus the dependency edges.
A declared dependency that is not installed in this environment is omitted (the
closure is bounded by what is importable, not by what is declared).

Built straight from installed metadata (no extra scanner dependency), so it
reflects exactly what is importable in this environment. Deterministic: components
are sorted and the serial is a UUIDv5 of the closure, with no wall-clock timestamp,
so identical environments produce byte-identical output. Together the two SBOMs
cover both axes a CRA / UNECE R155-R156 obligation cares about: the application
composition and the software supply chain. Never a certification artifact.
"""
from __future__ import annotations

import re
import uuid
import warnings
from importlib import metadata

from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.output import make_outputter
from cyclonedx.schema import OutputFormat, SchemaVersion
from packageurl import PackageURL
from packaging.requirements import Requirement

from loom.assurance.sbom import _license

ROOT = "loom"


def _norm(name: str) -> str:
    """PEP 503 normalized distribution name (the stable graph key)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _marker_ok(req: Requirement, extras: frozenset[str]) -> bool:
    """True if this requirement applies in the current env for the wanted extras."""
    if req.marker is None:
        return True
    if req.marker.evaluate():
        return True
    return any(req.marker.evaluate({"extra": e}) for e in extras)


def _dist_license(dist) -> str | None:
    """Best-effort license string from package metadata (PEP 639 expression first,
    then an OSI classifier, then the legacy ``License`` field — skipping dumped
    full-text license bodies)."""
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr.strip()
    osi = [
        c.rsplit("::", 1)[-1].strip()
        for c in (meta.get_all("Classifier") or [])
        if c.startswith("License :: OSI Approved")
    ]
    if osi:
        return osi[0]
    lic = meta.get("License")
    if lic and "\n" not in lic and len(lic) <= 64:
        return lic.strip()
    return None


def resolve_closure(root: str = ROOT) -> tuple[dict, dict]:
    """Walk the installed dependency graph from ``root``.

    Returns ``(nodes, edges)`` where ``nodes[key] = Distribution`` and
    ``edges[key] = [child_key, ...]``. Only base (non-extra) requirements are
    followed transitively, with environment markers evaluated, so the result is
    the actual runtime closure rather than the dev/test toolset.
    """
    nodes: dict[str, object] = {}
    edges: dict[str, set[str]] = {}
    to_visit: list[tuple[str, frozenset[str]]] = [(root, frozenset())]
    # Dedup by (name, extras): a package reached both plainly and via an extra must
    # be re-walked for the extra, or its extra-gated children are silently dropped.
    visited: set[tuple[str, frozenset[str]]] = set()
    while to_visit:
        name, extras = to_visit.pop()
        key = _norm(name)
        if (key, extras) in visited:
            continue
        visited.add((key, extras))
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        nodes[key] = dist
        children = edges.setdefault(key, set())  # union across re-walks, never clobber
        for req_str in dist.requires or []:
            req = Requirement(req_str)
            if not _marker_ok(req, extras):
                continue
            children.add(_norm(req.name))
            to_visit.append((req.name, frozenset(req.extras)))
    return nodes, {k: sorted(v) for k, v in edges.items()}


def _component(dist) -> Component:
    name = dist.metadata.get("Name") or "unknown"
    version = dist.version
    lic = _license(_dist_license(dist))
    return Component(
        name=name,
        type=ComponentType.LIBRARY,
        version=version,
        bom_ref=_norm(name),
        licenses=[lic] if lic else [],
        purl=PackageURL(type="pypi", name=_norm(name), version=version),
    )


def build_toolchain_sbom(root: str = ROOT) -> str:
    """Return a CycloneDX JSON SBOM string for the toolchain dependency closure."""
    nodes, edges = resolve_closure(root)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # silence CycloneDX dep-graph completeness notes
        bom = Bom()
        comps = {key: _component(nodes[key]) for key in sorted(nodes)}
        for key in sorted(comps):
            bom.components.add(comps[key])

        root_key = _norm(root)
        root_version = nodes[root_key].version if root_key in nodes else "0.0.0"
        app = Component(
            name=f"{root}-toolchain",
            type=ComponentType.APPLICATION,
            version=root_version,
            bom_ref=f"toolchain:{root}",
        )
        bom.metadata.component = app

        # Dependency edges: the synthetic root -> the root dist, then each dist ->
        # its installed direct deps (children that aren't installed are dropped).
        if root_key in comps:
            bom.register_dependency(app, [comps[root_key]])
        for key in sorted(edges):
            if key not in comps:
                continue
            children = [comps[c] for c in edges[key] if c in comps]
            if children:
                bom.register_dependency(comps[key], children)

        seed = "loom:toolchain:" + ",".join(
            f"{nodes[k].metadata.get('Name')}@{nodes[k].version}" for k in sorted(nodes)
        )
        bom.serial_number = uuid.uuid5(uuid.NAMESPACE_URL, seed)
        bom.metadata.timestamp = None
        return make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_6).output_as_string(indent=2)


def toolchain_component_count(root: str = ROOT) -> int:
    nodes, _ = resolve_closure(root)
    return len(nodes)
