"""Abstract orchestrator interface + run result."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from loom.bus.base import Bus
    from loom.module import Module
    from loom.monitors.engine import MonitorEngine
    from loom.plant.base import Plant
    from loom.sim.faults import FaultInjector
    from loom.sim.scenario import Scenario
    from loom.sim.stimulus import ScenarioStimulus
    from loom.sim.trace import Trace


@dataclass
class RunResult:
    orchestrator: str
    scenario: str
    steps: int
    duration_s: float
    changed_signals: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    violations: list = field(default_factory=list)


class Orchestrator(ABC):
    name: str = ""

    @abstractmethod
    def run(
        self,
        *,
        modules: "list[Module]",
        bus: "Bus",
        plant: "Plant | None",
        scenario: "Scenario",
        trace: "Trace",
        stimulus: "ScenarioStimulus | None" = None,
        faults: "FaultInjector | None" = None,
        monitors: "MonitorEngine | None" = None,
    ) -> RunResult:
        """Bring up modules + plant, drive the scenario, record the trace."""
