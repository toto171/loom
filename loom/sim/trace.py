"""Trace recorder — per-tick snapshots of the signal bus."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Trace:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def record(self, t: float, signals: dict[str, Any]) -> None:
        self.rows.append({"t": round(float(t), 6), "signals": dict(signals)})

    def series(self, path: str) -> list[tuple[float, Any]]:
        """Return the (t, value) time series for one VSS path."""
        return [(r["t"], r["signals"][path]) for r in self.rows if path in r["signals"]]

    def changed_signals(self) -> dict[str, tuple[Any, Any]]:
        """Map each path whose value changed over the run to (first, last)."""
        first: dict[str, Any] = {}
        last: dict[str, Any] = {}
        for row in self.rows:
            for path, value in row["signals"].items():
                first.setdefault(path, value)
                last[path] = value
        return {p: (first[p], last[p]) for p in first if first[p] != last[p]}

    def write_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for row in self.rows:
                fh.write(json.dumps(row) + "\n")
