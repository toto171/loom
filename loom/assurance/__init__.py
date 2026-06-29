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
