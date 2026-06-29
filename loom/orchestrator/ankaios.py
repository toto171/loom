"""Eclipse Ankaios orchestrator — a third Orchestrator implementation.

Ankaios is an automotive workload orchestrator (HPC/zonal ECUs). It plays the role
Docker-Compose plays for :class:`loom.orchestrator.compose.ComposeOrchestrator`:
it brings the workloads up. The signal backbone stays the networked KUKSA databroker
(:class:`loom.bus.kuksa.KuksaBus`), so once the workloads are running the scenario
is driven by the very same tick loop (:func:`loom.orchestrator._loop.drive`) — a
distributed Ankaios run therefore behaves identically to the in-process and Compose
runs.

Provisioning is injectable: pass a ``provisioner`` (an Ankaios control-interface
client exposing ``apply(desired_state)``) and a ``manifest`` (from
:func:`loom.deploy.ankaios.build_ankaios_manifest`) and the orchestrator applies the
desired state before driving. Tests inject a fake provisioner; a live cluster needs
an Ankaios runtime (``ank-server``/``ank-agent``) and built per-module images — the
same remaining packaging step noted for Compose.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

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


class AnkaiosOrchestrator(Orchestrator):
    name = "ankaios"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 55555,
        *,
        provisioner: Any = None,
        manifest: dict | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.provisioner = provisioner
        self.manifest = manifest

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
        from loom.bus.kuksa import KuksaBus

        # 1) Deploy the workloads via Ankaios (apply the desired state), if provisioned.
        if self.provisioner is not None and self.manifest is not None:
            self.provisioner.apply(self.manifest)

        # 2) Drive over the networked KUKSA bus — identical to Compose; Ankaios only
        #    changes who launches the workloads, not the signal backbone.
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
