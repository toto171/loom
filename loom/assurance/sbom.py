"""Vehicle SBOM generation (CycloneDX) — HANDOFF §8 M5.

Aggregates the composed modules into a CycloneDX **bill of modules** with their
declared SPDX licenses. v0 scope (honest): this is a module-level SBOM, not a
transitive software-dependency scan — it records the composed modules + the
plant + their declared licenses (feeding UNECE R155/R156 + EU CRA obligations),
not each module's library dependency tree. Never a certification artifact.
"""
from __future__ import annotations

import uuid
import warnings

from cyclonedx.model import Property
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model.license import DisjunctiveLicense
from cyclonedx.output import make_outputter
from cyclonedx.schema import OutputFormat, SchemaVersion
from cyclonedx.spdx import is_supported_id


def _license(spdx: str | None):
    if not spdx:
        return None
    # A recognized SPDX id goes in license.id; anything else (e.g.
    # LicenseRef-Proprietary) must use license.name to stay schema-valid.
    if is_supported_id(spdx):
        return DisjunctiveLicense(id=spdx)
    return DisjunctiveLicense(name=spdx)


def build_vehicle_sbom(vehicle_name, vehicle_class, modules, plant_impl=None) -> str:
    """Return a CycloneDX JSON SBOM string for the composed vehicle."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # silence CycloneDX dep-graph completeness notes
        bom = Bom()
        root = Component(
            name=vehicle_name,
            type=ComponentType.DEVICE,
            version="0.0.1",
            bom_ref=f"vehicle:{vehicle_name}",
            properties=[Property(name="loom:vehicleClass", value=str(vehicle_class or ""))],
        )
        bom.metadata.component = root

        dependencies = []
        for m in modules:
            contract = m.contract
            lic = _license(contract.license)
            comp = Component(
                name=contract.module,
                type=ComponentType.APPLICATION,
                version=contract.version,
                bom_ref=contract.module,
                licenses=[lic] if lic else [],
                properties=[Property(name="loom:safetyLevel", value=contract.safety_level)],
            )
            bom.components.add(comp)
            dependencies.append(comp)

        if plant_impl:
            plant = Component(
                name=f"plant.{plant_impl}",
                type=ComponentType.APPLICATION,
                version="0.0.1",
                bom_ref=f"plant.{plant_impl}",
            )
            bom.components.add(plant)
            dependencies.append(plant)

        bom.register_dependency(root, dependencies)

        # Reproducibility (HANDOFF §10.5): a deterministic serial derived from the
        # composition, and no wall-clock timestamp — identical inputs -> identical SBOM.
        seed = f"loom:{vehicle_name}:{plant_impl}:" + ",".join(
            sorted(m.contract.module for m in modules)
        )
        bom.serial_number = uuid.uuid5(uuid.NAMESPACE_URL, seed)
        bom.metadata.timestamp = None
        return make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_6).output_as_string(indent=2)


def sbom_component_count(modules, plant_impl=None) -> int:
    return len(list(modules)) + (1 if plant_impl else 0)
