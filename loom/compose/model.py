"""Typed model of a composition spec (§5.1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubsystemSelection:
    name: str
    impl: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Composition:
    name: str
    vehicle_class: str | None
    plant_impl: str
    plant_params: dict[str, Any]
    bus_type: str
    vss_release: str | None
    subsystems: list[SubsystemSelection]
    scenarios: list[str]
    raw: dict[str, Any] = field(default_factory=dict)

    def subsystem(self, name: str) -> SubsystemSelection | None:
        for sel in self.subsystems:
            if sel.name == name:
                return sel
        return None
