"""Loom error hierarchy."""
from __future__ import annotations


class LoomError(Exception):
    """Base class for all Loom errors."""


class ValidationError(LoomError):
    """A spec or contract failed JSON-Schema validation."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        self.errors = list(errors or [])
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        if self.errors:
            return base + ":\n  - " + "\n  - ".join(self.errors)
        return base


class ContractError(LoomError):
    """A module contract could not be loaded or is invalid."""


class ModuleResolutionError(LoomError):
    """A subsystem implementation could not be resolved to a Module."""


class StaticCheckFailed(LoomError):
    """The composition failed the fail-fast static contract check."""

    def __init__(self, report) -> None:
        self.report = report
        super().__init__(f"static check failed: {len(report.errors)} error(s)")


class GateRefused(LoomError):
    """A below-the-safety-line swap was refused by the gate (needs --revalidate)."""

    def __init__(self, decision) -> None:
        self.decision = decision
        super().__init__(decision.refused_reason or "swap gate refused")
