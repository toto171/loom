"""Load + JSON-Schema-validate a module ``contract.yaml`` into a Contract."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from loom.contracts.model import Contract, FailureMode, Signal
from loom.errors import ContractError
from loom.schema import SchemaName, validate_against


def _signals(items: list[dict[str, Any]] | None) -> list[Signal]:
    return [
        Signal(path=s["path"], unit=s.get("unit"), optional=bool(s.get("optional", False)))
        for s in (items or [])
    ]


def validate_contract_data(data: Any) -> list[str]:
    return validate_against(data, SchemaName.CONTRACT)


def parse_contract(data: dict[str, Any]) -> Contract:
    timing = data["timing"]
    signals = data.get("signals", {})
    return Contract(
        module=data["module"],
        version=data["version"],
        license=data["license"],
        safety_level=data["safetyLevel"],
        period_ms=float(timing["periodMs"]),
        deadline_ms=float(timing["deadlineMs"]),
        resource=timing.get("resource"),
        provides=_signals(signals.get("provides")),
        requires=_signals(signals.get("requires")),
        failure_modes=[
            FailureMode(
                id=f["id"],
                detect=f["detect"],
                effect=f["effect"],
                mitigation=f.get("mitigation"),
            )
            for f in data.get("failureModes", [])
        ],
        assume=list(data.get("assume", [])),
        guarantee=list(data.get("guarantee", [])),
        bindings=dict(data.get("bindings", {})),
        odd=dict(data.get("odd", {})),
        ai=dict(data.get("ai", {})),
        sbom_ref=data.get("sbomRef"),
        raw=data,
    )


def load_contract(path: str | Path) -> Contract:
    path = Path(path)
    if not path.exists():
        raise ContractError(f"contract not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContractError(f"invalid YAML in {path}: {exc}") from exc
    errors = validate_contract_data(data)
    if errors:
        raise ContractError(f"invalid contract {path}:\n  - " + "\n  - ".join(errors))
    return parse_contract(data)
