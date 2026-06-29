"""Assurance + compliance generation (M5) — aggregate a CycloneDX vehicle SBOM
and a GSN assurance-case skeleton (rendered to Mermaid) from contracts + check
results + runtime outcomes. Generated *skeletons / starting points*, never a
certification artifact (HANDOFF §10 principle 7, §11).
"""
from __future__ import annotations

from loom.assurance.gsn import Gsn, GsnLink, GsnNode, build_gsn, render_mermaid
from loom.assurance.sbom import (
    build_module_sbom,
    build_vehicle_sbom,
    module_sbom_ref,
    sbom_component_count,
    write_vehicle_sboms,
)

# NOTE: loom.assurance.deps (the toolchain SBOM) is intentionally NOT imported here.
# It is loaded lazily inside write_vehicle_sboms (under a try/except), so a problem
# with its dependency-metadata machinery degrades the toolchain SBOM to a no-op
# rather than breaking import of the whole assurance package (and with it run/cli/
# dashboard). Import it directly from loom.assurance.deps when you need it.

__all__ = [
    "Gsn",
    "GsnLink",
    "GsnNode",
    "build_gsn",
    "render_mermaid",
    "build_module_sbom",
    "build_vehicle_sbom",
    "module_sbom_ref",
    "sbom_component_count",
    "write_vehicle_sboms",
]
