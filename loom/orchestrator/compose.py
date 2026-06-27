"""Docker-Compose / KUKSA orchestrator — the distributed second Orchestrator impl.

It drives the scenario over a *networked* Eclipse KUKSA databroker (via KuksaBus)
instead of the in-process ShimBus, reusing the same tick loop as the in-process
orchestrator (loom.orchestrator._loop.drive) — so a distributed run behaves
identically. The repo's docker-compose.yml brings up the databroker; with full
per-module containerization each module service would connect to the same broker
(that packaging step is the remaining production work — see README).

Provisioning: ``run`` uses a KuksaBus if one is passed in (e.g. backed by an
injected client for testing), otherwise it connects to the configured databroker
address. Eclipse Ankaios can later replace Compose behind this same interface.
"""
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


class ComposeOrchestrator(Orchestrator):
    name = "compose"

    def __init__(self, host: str = "127.0.0.1", port: int = 55555) -> None:
        self.host = host
        self.port = port

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
        from loom.bus.kuksa import KuksaBus

        # Use the passed bus if it is already a KuksaBus (injected/testable);
        # otherwise provision + connect one to the configured databroker.
        if isinstance(bus, KuksaBus):
            kuksa_bus, owns = bus, False
        else:
            kuksa_bus, owns = KuksaBus(self.host, self.port).connect(), True
        try:
            return drive(
                name=self.name, modules=modules, bus=kuksa_bus, plant=plant,
                scenario=scenario, trace=trace, stimulus=stimulus, faults=faults,
                monitors=monitors,
            )
        finally:
            if owns:
                kuksa_bus.close()
