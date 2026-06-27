"""The shared simulation tick loop, used by every Orchestrator implementation.

Keeping the loop in one place means the InProcess (ShimBus) and Compose (networked
KUKSA broker) orchestrators differ only in *how the bus is provisioned*, not in how
the scenario is driven — so distributed runs behave identically to in-process ones.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loom.orchestrator.base import RunResult

if TYPE_CHECKING:
    from loom.bus.base import Bus
    from loom.module import Module
    from loom.monitors.engine import MonitorEngine
    from loom.plant.base import Plant
    from loom.sim.faults import FaultInjector
    from loom.sim.scenario import Scenario
    from loom.sim.stimulus import ScenarioStimulus
    from loom.sim.trace import Trace


def drive(
    *,
    name: str,
    modules: "list[Module]",
    bus: "Bus",
    plant: "Plant | None",
    scenario: "Scenario",
    trace: "Trace",
    stimulus: "ScenarioStimulus | None" = None,
    faults: "FaultInjector | None" = None,
    monitors: "MonitorEngine | None" = None,
) -> RunResult:
    """Drive the scenario over ``bus``. Tick order:
    stimulus -> plant.step -> faults.apply -> modules.step -> monitors -> record.
    The t=0 row is the seeded initial condition (state AT time t)."""
    if plant is not None:
        plant.start(bus)
    for module in modules:
        module.start(bus)

    truth: dict = dict(plant.truth()) if plant is not None else {}
    if stimulus is not None:
        stimulus.apply(0.0, bus)
    if faults is not None:
        faults.apply(0.0, bus)
    if monitors is not None:
        monitors.evaluate(0.0, bus, truth)
    trace.record(0.0, bus.snapshot())

    dt = scenario.dt_s
    steps = scenario.num_steps
    for i in range(1, steps + 1):
        t = i * dt
        if stimulus is not None:
            stimulus.apply(t, bus)
        if plant is not None:
            plant.step(t, dt, bus)
            truth = dict(plant.truth())
        if faults is not None:
            faults.apply(t, bus)
        crashed = faults.crashed_modules(t) if faults is not None else set()
        for module in modules:
            if module.module_id not in crashed:
                module.step(t, dt, bus)
        if monitors is not None:
            monitors.evaluate(t, bus, truth)
        trace.record(t, bus.snapshot())

    for module in modules:
        module.stop()
    if plant is not None:
        plant.stop()

    return RunResult(
        orchestrator=name,
        scenario=scenario.name,
        steps=steps + 1,
        duration_s=scenario.duration_s,
        changed_signals=trace.changed_signals(),
        violations=list(monitors.violations) if monitors is not None else [],
    )
