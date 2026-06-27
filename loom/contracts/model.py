"""Typed model of a module contract (§5.2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Signal:
    path: str
    unit: str | None = None
    optional: bool = False


@dataclass(frozen=True)
class FailureMode:
    id: str
    detect: str
    effect: str
    mitigation: str | None = None


@dataclass
class Contract:
    module: str
    version: str
    license: str
    safety_level: str
    period_ms: float
    deadline_ms: float
    resource: str | None = None
    provides: list[Signal] = field(default_factory=list)
    requires: list[Signal] = field(default_factory=list)
    failure_modes: list[FailureMode] = field(default_factory=list)
    assume: list[str] = field(default_factory=list)
    guarantee: list[str] = field(default_factory=list)
    bindings: dict[str, str] = field(default_factory=dict)
    odd: dict[str, Any] = field(default_factory=dict)
    ai: dict[str, Any] = field(default_factory=dict)
    sbom_ref: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def subsystem(self) -> str:
        return self.module.split(".", 1)[0]

    @property
    def impl(self) -> str:
        return self.module.split(".", 1)[1] if "." in self.module else ""

    @property
    def is_below_safety_line(self) -> bool:
        """True for ASIL-* modules (the re-validation-gated, below-line ones)."""
        return self.safety_level.upper().startswith("ASIL")
