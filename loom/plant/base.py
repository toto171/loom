"""Abstract physics plant model (FMI-style boundary)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loom.bus.base import Bus


class Plant(ABC):
    """The physics of the vehicle that software modules drive and sense.

    v0 ships a longitudinal + battery model behind this interface. A
    high-fidelity engine (Motoquant, RK4/Pacejka) — or any FMU loaded via FMPy —
    drops in by implementing the same ``step`` contract, with no change to the
    orchestrator or modules.
    """

    impl: str = ""
    # Signal manifest for the static checker (the plant is a valid signal
    # producer/consumer alongside modules). Lists of {"path", "unit"} dicts.
    provides: list[dict] = []
    requires: list[dict] = []

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params: dict[str, Any] = dict(params or {})

    def start(self, bus: Bus) -> None:
        """Optional hook: seed ground-truth signals before the first tick."""

    @abstractmethod
    def step(self, t: float, dt: float, bus: Bus) -> None:
        """Integrate the plant one tick and publish ground-truth signals."""

    def stop(self) -> None:
        """Optional hook: clean up after the run."""

    def truth(self) -> dict[str, Any]:
        """Sim-only ground-truth quantities for ``truth:`` monitor bindings
        (e.g. the true State-of-Charge a BMS estimate is compared against)."""
        return {}
