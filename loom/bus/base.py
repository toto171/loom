"""Abstract VSS signal backbone."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Bus(ABC):
    """A typed pub/sub backbone over COVESA VSS dotted paths.

    Modules and the plant publish/read VSS paths through this interface only, so
    the in-process ShimBus (M0/M1 fallback) and a future Eclipse KUKSA databroker
    implementation are interchangeable. Keep the boundary abstract.
    """

    @abstractmethod
    def publish(
        self,
        path: str,
        value: Any,
        *,
        unit: str | None = None,
        producer: str | None = None,
    ) -> None:
        """Write ``value`` to a VSS path (optionally recording unit + producer)."""

    @abstractmethod
    def read(self, path: str, default: Any = None) -> Any:
        """Read the latest value at a VSS path, or ``default`` if unset."""

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        """Return a copy of all current path -> value pairs (for trace recording)."""

    @abstractmethod
    def paths(self) -> list[str]:
        """Return all known VSS paths."""

    def unit_of(self, path: str) -> str | None:
        return None

    def producer_of(self, path: str) -> str | None:
        return None
