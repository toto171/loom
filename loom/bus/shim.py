"""In-process VSS shim broker (M0/M1 fallback for KUKSA).

A minimal pub/sub over VSS paths living entirely in one process. Because it is
in-process, modules sharing it must run in the same process — which is exactly
what the InProcessOrchestrator does. A networked KUKSA databroker (paired with
the ComposeOrchestrator) implements the same Bus interface for distributed runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loom.bus.base import Bus


@dataclass
class _Cell:
    value: Any = None
    unit: str | None = None
    producer: str | None = None


class ShimBus(Bus):
    def __init__(self) -> None:
        self._cells: dict[str, _Cell] = {}

    def publish(self, path, value, *, unit=None, producer=None) -> None:
        cell = self._cells.get(path)
        if cell is None:
            cell = _Cell()
            self._cells[path] = cell
        cell.value = value
        if unit is not None:
            cell.unit = unit
        if producer is not None:
            cell.producer = producer

    def read(self, path, default=None):
        cell = self._cells.get(path)
        return default if cell is None else cell.value

    def snapshot(self) -> dict[str, Any]:
        return {path: cell.value for path, cell in self._cells.items()}

    def paths(self) -> list[str]:
        return sorted(self._cells)

    def unit_of(self, path):
        cell = self._cells.get(path)
        return cell.unit if cell else None

    def producer_of(self, path):
        cell = self._cells.get(path)
        return cell.producer if cell else None
