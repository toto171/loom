"""M6 (plant swap): the higher-fidelity motoquant plant drops into the same FMI
boundary — switching plant.impl runs the same scenario with no module change, and
its thermal model makes battery temperature vary over the cycle."""
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.monitors.engine import MonitorEngine
from loom.orchestrator.inprocess import InProcessOrchestrator
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.sim.faults import FaultInjector
from loom.sim.scenario import load_scenario
from loom.sim.stimulus import ScenarioStimulus, interpolate_profile
from loom.sim.trace import Trace

SPEED = "Vehicle.Speed"
SOC = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"
TEMP = "Vehicle.Powertrain.TractionBattery.Temperature.Average"


def _run(spec_name):
    comp = load_composition(repo_root() / "spec" / spec_name)
    scen = load_scenario("urban_drive")
    bus = ShimBus()
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)
    trace = Trace()
    InProcessOrchestrator().run(
        modules=[m.instance for m in modules],
        bus=bus,
        plant=plant,
        scenario=scen,
        trace=trace,
        stimulus=ScenarioStimulus(scen),
        faults=FaultInjector(scen.faults),
        monitors=MonitorEngine.from_modules(modules),
    )
    return comp, scen, trace


def test_motoquant_plant_loads_with_the_same_signal_manifest():
    plant = load_plant("motoquant", {})
    paths = {s["path"] for s in plant.provides}
    assert plant.impl == "motoquant"
    assert SPEED in paths and TEMP in paths  # interchangeable with longitudinal


def test_motoquant_swap_speed_tracks_and_soc_drops():
    comp, scen, trace = _run("vehicle.motoquant.yaml")
    assert comp.plant_impl == "motoquant"
    errs = [abs(interpolate_profile(scen.profile, r["t"]) - r["signals"][SPEED]) for r in trace.rows]
    assert sum(errs) / len(errs) < 3.0  # still tracks the cycle
    socs = [r["signals"][SOC] for r in trace.rows]
    assert socs[-1] < socs[0]  # SoC drops


def test_motoquant_battery_temperature_varies():
    # Higher fidelity: the thermal model makes temp change over the cycle.
    _comp, _scen, trace = _run("vehicle.motoquant.yaml")
    temps = [r["signals"][TEMP] for r in trace.rows]
    assert max(temps) - min(temps) > 0.01


def test_longitudinal_battery_temperature_is_constant():
    # The v0 plant holds temperature constant — the contrast that motivates M6.
    _comp, _scen, trace = _run("vehicle.example.yaml")
    temps = [r["signals"][TEMP] for r in trace.rows]
    assert max(temps) - min(temps) < 1e-9


def test_plant_swap_changes_only_the_plant_not_the_modules():
    longitudinal = load_composition(repo_root() / "spec" / "vehicle.example.yaml")
    motoquant = load_composition(repo_root() / "spec" / "vehicle.motoquant.yaml")
    assert longitudinal.plant_impl == "longitudinal"
    assert motoquant.plant_impl == "motoquant"
    long_subs = {s.name: s.impl for s in longitudinal.subsystems}
    mq_subs = {s.name: s.impl for s in motoquant.subsystems}
    assert long_subs == mq_subs  # identical module set -> no other code change
