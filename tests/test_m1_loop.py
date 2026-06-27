"""M1 acceptance + integration: the full example composition drives a complete
cross-module control loop — speed tracks the cycle and SoC drops."""
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.orchestrator.inprocess import InProcessOrchestrator
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.sim.scenario import load_scenario
from loom.sim.stimulus import ScenarioStimulus, interpolate_profile
from loom.sim.trace import Trace

SPEED = "Vehicle.Speed"
SOC = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"
LKA = "Vehicle.ADAS.LaneKeepingAssist.IsEngaged"
BRAKE = "Vehicle.Body.Lights.Brake.IsActive"


def _run_example():
    comp = load_composition(repo_root() / "spec" / "vehicle.example.yaml")
    scen = load_scenario("urban_drive")
    bus = ShimBus()
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)
    trace = Trace()
    result = InProcessOrchestrator().run(
        modules=[m.instance for m in modules],
        bus=bus,
        plant=plant,
        scenario=scen,
        trace=trace,
        stimulus=ScenarioStimulus(scen),
    )
    return comp, scen, modules, result, trace


def test_all_five_reference_modules_resolve():
    _comp, _scen, modules, _result, _trace = _run_example()
    assert sorted(m.module_id for m in modules) == [
        "adas.adas_stub",
        "bms.default",
        "body.default",
        "hmi.default",
        "powertrain.default",
    ]


def test_speed_tracks_the_cycle():
    _comp, scen, _modules, _result, trace = _run_example()
    errs = [
        abs(interpolate_profile(scen.profile, r["t"]) - r["signals"][SPEED])
        for r in trace.rows
    ]
    assert max(errs) < 6.0
    assert sum(errs) / len(errs) < 2.0
    # reaches cruising speed mid-cycle (target 50 km/h at t=8)
    at8 = next(r for r in trace.rows if abs(r["t"] - 8.0) < 1e-9)
    assert at8["signals"][SPEED] > 45.0


def test_soc_drops_over_cycle():
    _comp, _scen, _modules, result, _trace = _run_example()
    first, last = result.changed_signals[SOC]
    assert first == 80.0
    assert last < first


def test_regen_recovers_energy_during_deceleration():
    # SoC should tick back up across a braking phase (regen) relative to a
    # pure-discharge model: find a window where SoC increases.
    _comp, _scen, _modules, _result, trace = _run_example()
    socs = [r["signals"][SOC] for r in trace.rows]
    assert any(b > a for a, b in zip(socs, socs[1:], strict=False))


def test_adas_engages_only_within_odd():
    _comp, _scen, _modules, _result, trace = _run_example()
    assert any(r["signals"][LKA] for r in trace.rows)  # engages at some point
    for r in trace.rows:
        if r["signals"][SPEED] > 80.0:  # ODD speed cap
            assert r["signals"][LKA] is False


def test_brake_light_activates_during_deceleration():
    _comp, _scen, _modules, _result, trace = _run_example()
    assert any(r["signals"][BRAKE] for r in trace.rows)


def test_no_duplicate_signal_producers():
    # Integration preview of the M2 producer-uniqueness rule: across the example
    # composition, no VSS path is provided by two modules.
    _comp, _scen, modules, _result, _trace = _run_example()
    seen: dict[str, str] = {}
    for m in modules:
        for sig in m.contract.provides:
            assert sig.path not in seen, (
                f"{sig.path} produced by both {seen.get(sig.path)} and {m.module_id}"
            )
            seen[sig.path] = m.module_id
