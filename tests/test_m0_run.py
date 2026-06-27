"""Automated M0 acceptance: `loom run` on the M0 spec produces a trace in which
one VSS signal (battery SoC) is observed changing."""
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.orchestrator.inprocess import InProcessOrchestrator
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.sim.scenario import load_scenario
from loom.sim.trace import Trace

SOC = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"


def _run_m0():
    comp = load_composition(repo_root() / "spec" / "vehicle.m0.yaml")
    scen = load_scenario(comp.scenarios[0])
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
    )
    return comp, scen, result, trace


def test_soc_signal_changes_over_run():
    _comp, _scen, result, _trace = _run_m0()
    assert SOC in result.changed_signals
    first, last = result.changed_signals[SOC]
    assert last < first  # discharging over the drive cycle


def test_t0_row_is_initial_condition():
    # The first trace row is t=0 with the seeded initial SoC (80.0), not a
    # post-step value — i.e. no discharge has been integrated at the initial instant.
    _comp, _scen, _result, trace = _run_m0()
    series = trace.series(SOC)
    assert series[0] == (0.0, 80.0)


def test_trace_has_one_row_per_step():
    _comp, _scen, result, trace = _run_m0()
    series = trace.series(SOC)
    assert len(series) == result.steps
    assert result.steps == _scen_num_steps() + 1


def _scen_num_steps():
    from loom.sim.scenario import load_scenario

    return load_scenario("urban_drive").num_steps


def test_module_resolution_yields_bms_default():
    comp, _scen, _result, _trace = _run_m0()
    modules = resolve_modules(comp)
    assert [m.module_id for m in modules] == ["bms.default"]
