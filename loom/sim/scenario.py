"""Scenario model + loader.

A scenario is a timed stimulus (``durationS`` + ``stepMs`` drive the sim loop;
``profile`` is consumed by the plant at M1+) plus optional fault injection
(parsed now, acted on by the fault injector at M3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from loom.errors import LoomError
from loom.paths import scenarios_dir


@dataclass
class Fault:
    kind: str  # dropout | stuck | latency | crash
    target: str | None = None
    from_s: float = 0.0
    to_s: float = float("inf")
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    duration_s: float
    step_ms: float
    profile: list[dict[str, Any]] = field(default_factory=list)
    faults: list[Fault] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def dt_s(self) -> float:
        return self.step_ms / 1000.0

    @property
    def num_steps(self) -> int:
        return int(round(self.duration_s / self.dt_s))


def parse_scenario(data: dict[str, Any]) -> Scenario:
    faults = [
        Fault(
            kind=f["kind"],
            target=f.get("target"),
            from_s=float(f.get("fromS", 0.0)),
            to_s=float(f.get("toS", float("inf"))),
            raw=f,
        )
        for f in data.get("faults", [])
    ]
    return Scenario(
        name=data["name"],
        duration_s=float(data["durationS"]),
        step_ms=float(data["stepMs"]),
        profile=list(data.get("profile", [])),
        faults=faults,
        raw=data,
    )


def load_scenario(name: str) -> Scenario:
    path = scenarios_dir() / f"{name}.yaml"
    if not path.exists():
        raise LoomError(f"scenario '{name}' not found at {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LoomError(f"invalid YAML in {path}: {exc}") from exc
    return parse_scenario(data)
