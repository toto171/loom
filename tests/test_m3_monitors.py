"""M3 monitor engine: building monitors from contracts + bindings, binding
resolution, and firing on failure / unavailable-signal."""
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.monitors.engine import Monitor, MonitorEngine, resolve_bindings
from loom.paths import repo_root


def _modules():
    comp = load_composition(repo_root() / "spec" / "vehicle.example.yaml")
    return resolve_modules(comp)


def test_engine_builds_bound_monitors_and_records_skipped():
    eng = MonitorEngine.from_modules(_modules())
    live = {(m.module, m.monitor_id) for m in eng.monitors}
    assert ("bms.default", "temp_sensor_fault") in live
    assert ("bms.default", "soc_estimate_drift") in live
    assert ("adas.adas_stub", "odd_exit_undetected") in live
    skipped = {(s["module"], s["monitor"]) for s in eng.skipped}
    assert ("hmi.default", "display_stale") in skipped  # references unbindable 'now'
    assert ("body.default", "brake_light_stuck_off") in skipped


def test_resolve_bindings_signal_truth_const():
    bus = ShimBus()
    bus.publish("Vehicle.X", 5.0)
    variables = resolve_bindings(
        {"a": "signal:Vehicle.X", "b": "truth:soc", "c": "const:42"}, bus, {"soc": 80}
    )
    assert variables == {"a": 5.0, "b": 80, "c": 42.0}


def test_monitor_fires_on_failure_condition():
    eng = MonitorEngine([Monitor("m.default", "fm", "temp > 60", {"temp": "signal:Vehicle.T"}, "degraded")])
    bus = ShimBus()
    bus.publish("Vehicle.T", 70)
    fired = eng.evaluate(1.0, bus, {})
    assert len(fired) == 1 and fired[0].kind == "failure_detected"


def test_monitor_fires_on_unavailable_signal():
    eng = MonitorEngine([Monitor("m.default", "fm", "temp > 60", {"temp": "signal:Vehicle.T"}, "loss_of_function")])
    bus = ShimBus()
    bus.publish("Vehicle.T", None)
    fired = eng.evaluate(2.0, bus, {})
    assert len(fired) == 1 and fired[0].kind == "signal_unavailable" and fired[0].t == 2.0


def test_monitor_silent_when_nominal():
    eng = MonitorEngine([Monitor("m.default", "fm", "temp > 60", {"temp": "signal:Vehicle.T"}, "degraded")])
    bus = ShimBus()
    bus.publish("Vehicle.T", 25)
    assert eng.evaluate(1.0, bus, {}) == []


def test_monitor_records_error_on_type_confused_signal():
    # A non-numeric signal reaching a numeric predicate is contained as a
    # monitor_error violation, not an uncaught crash.
    eng = MonitorEngine([Monitor("m.default", "fm", "temp < 60", {"temp": "signal:Vehicle.T"}, "degraded")])
    bus = ShimBus()
    bus.publish("Vehicle.T", "hot")
    fired = eng.evaluate(1.0, bus, {})
    assert len(fired) == 1 and fired[0].kind == "monitor_error"
