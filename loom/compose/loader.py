"""Load + JSON-Schema-validate a composition spec into a Composition."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from loom.compose.model import Composition, SubsystemSelection
from loom.errors import ValidationError
from loom.schema import SchemaName, validate_against


def validate_composition_data(data: Any) -> list[str]:
    return validate_against(data, SchemaName.COMPOSITION)


def parse_composition(data: dict[str, Any]) -> Composition:
    meta = data["metadata"]
    plant = data["plant"]
    bus = data["bus"]
    subsystems = [
        SubsystemSelection(name=name, impl=sel["impl"], params=dict(sel.get("params", {})))
        for name, sel in data["subsystems"].items()
    ]
    return Composition(
        name=meta["name"],
        vehicle_class=meta.get("vehicleClass"),
        plant_impl=plant["impl"],
        plant_params=dict(plant.get("params", {})),
        bus_type=bus["type"],
        vss_release=bus.get("vssRelease"),
        subsystems=subsystems,
        scenarios=list(data["scenarios"]),
        raw=data,
    )


def load_composition(path: str | Path) -> Composition:
    path = Path(path)
    if not path.exists():
        raise ValidationError(f"composition spec not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValidationError(f"invalid YAML in {path}: {exc}") from exc
    errors = validate_composition_data(data)
    if errors:
        raise ValidationError(f"invalid composition {path}", errors)
    return parse_composition(data)
