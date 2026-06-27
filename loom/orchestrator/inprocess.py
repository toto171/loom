"""In-process orchestrator: tick modules + plant in one process over the ShimBus."""
from __future__ import annotations

from typing import TYPE_CHECKING

from loom.orchestrator._loop import drive
from loom.orchestrator.base import Orchestrator, RunResult

if TYPE_CHECKING:
    from loom.bus.base import Bus
    from loom.module import Module
    from loom.monitors.engine import MonitorEngine
    from loom.plant.base import Plant
    from loom.sim.faults import FaultInjector
    from loom.sim.scenario import Scenario
    from loom.sim.stimulus import ScenarioStimulus
    from loom.sim.trace import Trace


class InProcessOrchestrator(Orchestrator):
    """Runs everything synchronously in one process, sharing the in-process bus.

    Loop per tick: stimulus -> plant.step -> faults.apply -> each module.step ->
    monitors.evaluate -> record snapshot (see loom.orchestrator._loop.drive). Pairs
    with ShimBus; the ComposeOrchestrator (networked KUKSA broker) reuses the same
    loop over a networked bus.
    """

    name = "inprocess"

    def run(
        self,
        *,
        modules: list[Module],
        bus: Bus,
        plant: Plant | None,
        scenario: Scenario,
        trace: Trace,
        stimulus: ScenarioStimulus | None = None,
        faults: FaultInjector | None = None,
        monitors: MonitorEngine | None = None,
    ) -> RunResult:
        return drive(
            name=self.name, modules=modules, bus=bus, plant=plant, scenario=scenario,
            trace=trace, stimulus=stimulus, faults=faults, monitors=monitors,
        )
