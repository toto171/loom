"""Automated M3 acceptance: a battery-temp sensor dropout trips the BMS monitor,
and a clean run produces no violations."""
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.monitors.engine import MonitorEngine
from loom.orchestrator.inprocess import InProcessOrchestrator
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.sim.faults import FaultInjector
from loom.sim.scenario import load_scenario
from loom.sim.stimulus import ScenarioStimulus
from loom.sim.trace import Trace


def _run(scenario_name):
    comp = load_composition(repo_root() / "spec" / "vehicle.example.yaml")
    scen = load_scenario(scenario_name)
    bus = ShimBus()
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)
    monitors = MonitorEngine.from_modules(modules)
    result = InProcessOrchestrator().run(
        modules=[m.instance for m in modules],
        bus=bus,
        plant=plant,
        scenario=scen,
        trace=Trace(),
        stimulus=ScenarioStimulus(scen),
        faults=FaultInjector(scen.faults),
        monitors=monitors,
    )
    return result


def test_clean_run_has_no_violations():
    assert _run("urban_drive").violations == []


def test_temp_dropout_trips_bms_monitor_with_timestamp():
    result = _run("sensor_dropout_test")
    temp_viol = [
        v for v in result.violations
        if v.module == "bms.default" and v.monitor_id == "temp_sensor_fault"
    ]
    assert temp_viol, "expected the BMS temp_sensor_fault monitor to trip"
    assert all(v.kind == "signal_unavailable" for v in temp_viol)
    timestamps = [v.t for v in temp_viol]
    # the dropout window is t in [8, 12] (scenarios/sensor_dropout_test.yaml)
    assert min(timestamps) >= 8.0
    assert max(timestamps) <= 12.0


def test_soc_drift_monitor_stays_green_in_nominal():
    # BMS estimate tracks plant ground truth -> no drift violation in a clean run.
    result = _run("urban_drive")
    assert not any(v.monitor_id == "soc_estimate_drift" for v in result.violations)
