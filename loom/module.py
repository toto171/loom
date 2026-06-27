"""The Module base class — what every subsystem implementation realizes."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loom.bus.base import Bus


class Module(ABC):
    """A containerizable subsystem implementation, ticked by an orchestrator.

    For the M0/M1 in-process orchestrator, modules are ticked objects sharing the
    in-process ShimBus. The same class can later run as a standalone container
    service against a networked KUKSA broker; ``step`` is the per-tick behavior.
    """

    subsystem: str = ""
    impl: str = ""

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params: dict[str, Any] = dict(params or {})

    @property
    def module_id(self) -> str:
        return f"{self.subsystem}.{self.impl}"

    def start(self, bus: Bus) -> None:
        """Optional hook: declare/seed signals before the first tick."""

    @abstractmethod
    def step(self, t: float, dt: float, bus: Bus) -> None:
        """Advance one tick at sim time ``t`` seconds over interval ``dt`` seconds."""

    def stop(self) -> None:
        """Optional hook: clean up after the run completes."""
