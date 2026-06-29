"""Regression tests for the bugs surfaced by the multi-agent code audit.

Each test pins a fix that the previously-green suite did not catch (mostly latent
edge cases — empty/zero/None inputs, malformed state, path traversal). Grouped here
so the fixes can't silently regress.
"""

import pytest

from loom.bus.shim import ShimBus
from loom.monitors.engine import Monitor, MonitorEngine
from loom.sim.trace import Trace

# --- monitors: a malformed binding must be contained, not crash the whole tick ---


def test_malformed_binding_is_contained_and_other_monitors_still_fire():
    bus = ShimBus()
    bus.publish("Vehicle.X", 5.0)
    eng = MonitorEngine(monitors=[
        Monitor("a", "m1", "x > 1", {"x": "signal:Vehicle.X"}, "degraded"),
        Monitor("b", "bad", "y > 1", {"y": "const:notanumber"}, "degraded"),  # non-numeric const
        Monitor("c", "m2", "x > 1", {"x": "signal:Vehicle.X"}, "degraded"),
    ])
    fired = {(v.module, v.kind) for v in eng.evaluate(1.0, bus)}
    # the malformed monitor is contained, and a + c are NOT dropped
    assert ("b", "monitor_error") in fired
    assert ("a", "failure_detected") in fired
    assert ("c", "failure_detected") in fired


def test_non_boolean_detect_surfaces_a_monitor_error_not_silence():
    bus = ShimBus()
    bus.publish("Vehicle.X", 5.0)
    eng = MonitorEngine(monitors=[Monitor("a", "m", "x", {"x": "signal:Vehicle.X"}, "degraded")])
    fired = eng.evaluate(1.0, bus)
    assert [v.kind for v in fired] == ["monitor_error"]


# --- safety gate: fail safe on a corrupt/non-dict lock; gate malformed removals ---


def test_load_lock_fails_safe_on_corrupt_and_non_dict(tmp_path):
    from loom.errors import LoomError
    from loom.safety.gate import load_lock

    assert load_lock(tmp_path / "absent.json") is None  # missing -> no baseline
    bad = tmp_path / "bad.lock.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(LoomError):
        load_lock(bad)
    lst = tmp_path / "list.lock.json"
    lst.write_text("[1, 2, 3]", encoding="utf-8")  # truthy non-dict
    with pytest.raises(LoomError):
        load_lock(lst)


def test_removing_a_subsystem_with_missing_locked_safety_level_gates():
    from loom.safety.gate import detect_swaps, gate

    lock = {"subsystems": {"bms": {"impl": "default"}}}  # no safetyLevel recorded
    swaps = detect_swaps(current={}, lock=lock)  # bms removed
    assert swaps and swaps[0].below_line  # fails safe -> gated
    assert not gate(swaps, revalidate=False).allowed


# --- resolve: a missing impl contract must NOT inherit the default's safety level ---


def _write_brake_module(tmp_path, *, with_bbw_contract: bool):
    brake = tmp_path / "brake"
    brake.mkdir()
    (brake / "service.py").write_text(
        "from loom.module import Module\n"
        "class _D(Module):\n    subsystem='brake'\n    impl='default'\n"
        "    def step(self, t, dt, bus): pass\n"
        "class _B(Module):\n    subsystem='brake'\n    impl='bbw'\n"
        "    def step(self, t, dt, bus): pass\n"
        "IMPLEMENTATIONS={'default': _D, 'bbw': _B}\n",
        encoding="utf-8",
    )
    base = (
        "apiVersion: loom/v0\nkind: Contract\nmodule: brake.{mod}\nversion: 0.1.0\n"
        "license: Apache-2.0\nsafetyLevel: {lvl}\ntiming:\n  periodMs: 10\n  deadlineMs: 5\n"
        "signals:\n  provides:\n    - path: Vehicle.Brake.X\n"
    )
    (brake / "contract.yaml").write_text(base.format(mod="default", lvl="QM"), encoding="utf-8")
    if with_bbw_contract:
        (brake / "contract.bbw.yaml").write_text(
            base.format(mod="bbw", lvl="ASIL-D"), encoding="utf-8"
        )


def test_missing_impl_contract_is_rejected_not_inherited(tmp_path, monkeypatch):
    import loom.compose.resolve as rz
    from loom.errors import ModuleResolutionError

    _write_brake_module(tmp_path, with_bbw_contract=False)
    monkeypatch.setattr(rz, "modules_dir", lambda: tmp_path)
    rz._SERVICE_CACHE.clear()
    assert rz.resolve_module("brake", "default").contract.safety_level == "QM"
    # bbw has no contract.bbw.yaml: the fallback would hand it brake.default's QM
    # contract — the identity check must reject that rather than mis-label its safety.
    with pytest.raises(ModuleResolutionError):
        rz.resolve_module("brake", "bbw")


def test_present_impl_contract_resolves_with_its_own_identity(tmp_path, monkeypatch):
    import loom.compose.resolve as rz

    _write_brake_module(tmp_path, with_bbw_contract=True)
    monkeypatch.setattr(rz, "modules_dir", lambda: tmp_path)
    rz._SERVICE_CACHE.clear()
    rm = rz.resolve_module("brake", "bbw")
    assert rm.contract.module == "brake.bbw" and rm.contract.safety_level == "ASIL-D"


# --- checker: an underscored VSS path in an assumption must not be truncated ---


def test_assumption_with_underscored_vss_path_is_not_a_false_positive():
    from loom.contracts.checker import Participant, check_participants
    from loom.contracts.model import Signal

    report = check_participants("v", [
        Participant(name="p", provides=[Signal("Vehicle.Cabin.Door_Count")], is_module=True,
                    license="Apache-2.0"),
        Participant(name="c", requires=[Signal("Vehicle.Cabin.Door_Count")],
                    assume=["Vehicle.Cabin.Door_Count is available"], is_module=True,
                    license="Apache-2.0"),
    ])
    assert not [i for i in report.errors if i.rule == "assume_guarantee"]


# --- HMI: a genuine SoC of 0.0 must fire the low-battery warning ---


def test_hmi_warns_at_zero_soc():
    import importlib.util

    from loom.paths import repo_root

    spec = importlib.util.spec_from_file_location(
        "_hmi_svc", repo_root() / "modules" / "hmi" / "service.py"
    )
    svc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(svc)
    bus = ShimBus()
    bus.publish("Vehicle.Powertrain.TractionBattery.StateOfCharge.Current", 0.0)
    svc.HmiDefault({}).step(1.0, 0.1, bus)
    assert bus.read("Vehicle.Cabin.HMI.IsLowBatteryWarningActive") is True


# --- trace: a signal that departs and returns to its initial value is detected ---


def test_changed_signals_detects_a_transient_that_recovers():
    tr = Trace()
    for t, v in [(0.0, 1), (1.0, 99), (2.0, 1)]:
        tr.record(t, {"S": v})
    assert "S" in tr.changed_signals()


# --- bus: snapshot key order is deterministic and identical across the two buses ---


def test_shim_and_kuksa_snapshot_key_order_match_and_are_sorted():
    from loom.bus.kuksa import KuksaBus

    class _Fake:
        def __init__(self):
            self.store = {}

        def set_current_values(self, m):
            self.store.update(m)

        def get_current_values(self, paths):
            return {p: self.store.get(p) for p in paths}

    order = ["Vehicle.Speed", "Vehicle.ADAS.X", "Vehicle.Body.Y"]
    shim = ShimBus()
    kuk = KuksaBus(client=_Fake())
    for p in order:
        shim.publish(p, 1.0)
        kuk.publish(p, 1.0)
    assert list(shim.snapshot()) == sorted(order)
    assert list(kuk.snapshot()) == sorted(order)


# --- catalog: run_artifact must reject a traversal run_id ---


def test_run_artifact_rejects_traversal():
    from loom.catalog import run_artifact

    assert run_artifact("..", "pyproject.toml") is None
    assert run_artifact("../loom", "run.py") is None
    assert run_artifact("../../etc", "passwd") is None


def test_load_run_returns_none_on_corrupt_run_json(tmp_path, monkeypatch):
    import loom.catalog as cat

    monkeypatch.setattr(cat, "runs_dir", lambda: tmp_path)
    d = tmp_path / "20260101T000000000000-x"
    d.mkdir()
    (d / "run.json").write_text("{ broken", encoding="utf-8")
    assert cat.load_run(d.name) is None  # 404, not a 500


# --- predicate: a pathologically deep expression is contained, not a RecursionError ---


def test_deeply_nested_predicate_is_contained():
    from loom.monitors.predicate import PredicateError, evaluate

    expr = "(" * 2000 + "x" + ")" * 2000
    with pytest.raises(PredicateError):
        evaluate(expr, {"x": 1})


# --- run pipeline: two runs of one vehicle don't collide / overwrite ---


def test_two_runs_get_distinct_dirs(tmp_path, monkeypatch):
    import loom.run as run_mod
    from loom.paths import repo_root

    monkeypatch.setattr(run_mod, "runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(run_mod, "locks_dir", lambda: tmp_path / "locks")
    spec = repo_root() / "spec" / "vehicle.example.yaml"
    a = run_mod.execute_run(spec, "urban_drive")
    b = run_mod.execute_run(spec, "urban_drive")
    assert a.run_id != b.run_id
    assert a.run_dir.exists() and b.run_dir.exists()
    # the first run's trace was not clobbered by the second
    assert (a.run_dir / "trace.jsonl").exists()


# --- ADAS: a params ODD override is honored by the odd_exit monitor binding ---


def test_adas_odd_override_is_tracked_by_the_monitor_binding():
    from loom.compose.resolve import resolve_module
    from loom.monitors.engine import MonitorEngine

    rm = resolve_module("adas", "adas_stub", {"odd": {"speedMaxKph": 100.0}})
    eng = MonitorEngine.from_modules([rm])
    mon = next(m for m in eng.monitors if m.monitor_id == "odd_exit_undetected")
    bus = ShimBus()
    rm.instance.start(bus)
    # at 90 km/h the LKA is inside the *overridden* 100 km/h ODD, so engaged + no exit
    bus.publish("Vehicle.ADAS.CruiseControl.IsActive", True)
    bus.publish("Vehicle.Speed", 90.0)
    rm.instance.step(1.0, 0.1, bus)
    fired = eng.evaluate(1.0, bus)
    assert not any(v.monitor_id == "odd_exit_undetected" and v.kind == "failure_detected"
                   for v in fired)
    assert bus.read("Vehicle.ADAS.LaneKeepingAssist.OddSpeedMaxKph") == 100.0
    assert mon.bindings["odd_speed_max_kph"].startswith("signal:")
