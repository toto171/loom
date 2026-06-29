"""M2 static contract checker — each §5.2 rule with passing + failing fixtures,
plus end-to-end checks on the real example and a deliberately broken composition."""
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.contracts.checker import (
    Participant,
    check_composition,
    check_participants,
)
from loom.contracts.model import Signal
from loom.contracts.report import render_report
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.sim.stimulus import ScenarioStimulus


def _rules_with_errors(report):
    return {i.rule for i in report.errors}


# --- end-to-end on the real composition --------------------------------------

def _check_spec(name):
    comp = load_composition(repo_root() / "spec" / name)
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)
    return check_composition(
        comp.name, modules, plant=plant, stimulus_provides=ScenarioStimulus.provides
    )


def test_example_composition_passes_cleanly():
    report = _check_spec("vehicle.example.yaml")
    assert report.ok, [i.message for i in report.errors]
    assert report.errors == []
    assert report.warnings == []  # every assumption references a produced VSS path


def test_m0_composition_passes_with_optional_torque_warning():
    report = _check_spec("vehicle.m0.yaml")
    assert report.ok  # no errors
    # the plant optionally requires torque; with no powertrain that's a warning
    assert any(
        i.rule == "signal_resolution" and i.severity == "warning" and "Torque" in i.message
        for i in report.warnings
    )


def test_broken_spec_fails_with_unresolved_signal_message():
    report = _check_spec("vehicle.broken.yaml")
    assert not report.ok
    assert "signal_resolution" in _rules_with_errors(report)
    # precise message names the unresolved SoC path the hmi module requires
    msgs = " ".join(i.message for i in report.errors)
    assert "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current" in msgs
    assert "hmi.default" in msgs


def test_report_renders_for_example():
    report = _check_spec("vehicle.example.yaml")
    text = render_report(report)
    assert "Composition check — toy-ev-l7" in text
    assert "Signal graph" in text
    assert "[PASS] producer_uniqueness" in text
    assert "Result: OK" in text


# --- per-rule unit fixtures (synthetic participants) -------------------------

def _module(name, provides=(), requires=(), period=10, deadline=5, assume=(),
            resource=None, license="Apache-2.0"):
    return Participant(
        name=name,
        provides=[Signal(*p) if isinstance(p, tuple) else p for p in provides],
        requires=[Signal(*r) if isinstance(r, tuple) else r for r in requires],
        period_ms=period,
        deadline_ms=deadline,
        assume=list(assume),
        resource=resource,
        license=license,
        is_module=True,
    )


def test_signal_resolution_pass_and_fail():
    ok = check_participants("v", [
        _module("a.default", provides=[("Vehicle.X",)]),
        _module("b.default", requires=[("Vehicle.X",)]),
    ])
    assert ok.ok

    bad = check_participants("v", [_module("b.default", requires=[("Vehicle.X",)])])
    assert not bad.ok
    assert "signal_resolution" in _rules_with_errors(bad)


def test_producer_uniqueness_pass_and_fail():
    ok = check_participants("v", [
        _module("a.default", provides=[("Vehicle.A",)]),
        _module("b.default", provides=[("Vehicle.B",)]),
    ])
    assert "producer_uniqueness" not in _rules_with_errors(ok)

    bad = check_participants("v", [
        _module("a.default", provides=[("Vehicle.X",)]),
        _module("b.default", provides=[("Vehicle.X",)]),
    ])
    assert "producer_uniqueness" in _rules_with_errors(bad)
    msg = next(i.message for i in bad.errors if i.rule == "producer_uniqueness")
    assert "a.default" in msg and "b.default" in msg  # names both conflicting producers


def test_unit_consistency_pass_and_fail():
    ok = check_participants("v", [
        _module("a.default", provides=[Signal("Vehicle.X", "km/h")]),
        _module("b.default", requires=[Signal("Vehicle.X", "km/h")]),
    ])
    assert ok.ok

    bad = check_participants("v", [
        _module("a.default", provides=[Signal("Vehicle.X", "m/s")]),
        _module("b.default", requires=[Signal("Vehicle.X", "km/h")]),
    ])
    assert "unit_consistency" in _rules_with_errors(bad)


def test_timing_deadline_exceeds_period():
    bad = check_participants("v", [_module("a.default", period=10, deadline=15)])
    assert "timing" in _rules_with_errors(bad)
    msg = next(i.message for i in bad.errors if i.rule == "timing")
    assert "deadline" in msg and "15" in msg and "10" in msg  # precise numbers


def test_timing_overcommit_on_shared_resource():
    bad = check_participants("v", [
        _module("a.default", provides=[("Vehicle.A",)], period=10, deadline=6, resource="core0"),
        _module("b.default", provides=[("Vehicle.B",)], period=10, deadline=6, resource="core0"),
    ])
    # 0.6 + 0.6 = 1.2 > 1.0 on shared core0
    assert any("overcommit" in i.message and "core0" in i.message for i in bad.errors)


def test_no_overcommit_when_modules_on_separate_resources():
    # Same heavy load, but each on its own (default) resource -> no contention.
    ok = check_participants("v", [
        _module("a.default", provides=[("Vehicle.A",)], period=10, deadline=6),
        _module("b.default", provides=[("Vehicle.B",)], period=10, deadline=6),
    ])
    assert ok.ok


def test_optional_unresolved_require_is_warning_not_error():
    report = check_participants("v", [
        _module("p.default", requires=[Signal("Vehicle.Missing", optional=True)]),
    ])
    assert report.ok
    assert any(i.rule == "signal_resolution" and i.severity == "warning" for i in report.issues)


def test_assume_guarantee_undischarged_path_is_error():
    bad = check_participants("v", [
        _module("a.default", assume=["Vehicle.Missing.Signal must be present"]),
    ])
    assert "assume_guarantee" in _rules_with_errors(bad)


def test_assume_guarantee_satisfied_when_path_produced():
    ok = check_participants("v", [
        _module("p.default", provides=[("Vehicle.Cabin.Temp",)]),
        _module("a.default", assume=["Vehicle.Cabin.Temp between 18 and 24"]),
    ])
    assert ok.ok


def test_assume_without_vss_path_is_warning_not_error():
    report = check_participants("v", [_module("a.default", assume=["the road is dry"])])
    assert report.ok  # warning only, not an error
    assert any(i.rule == "assume_guarantee" and i.severity == "warning" for i in report.issues)


def test_self_discharged_assumption_is_error():
    # A module that both produces and assumes about a path does NOT discharge its
    # own precondition (§5.2: discharged by another module or the plant).
    bad = check_participants("v", [
        _module("a.default", provides=[("Vehicle.Foo",)], assume=["Vehicle.Foo between 1 and 2"]),
    ])
    assert "assume_guarantee" in _rules_with_errors(bad)


def test_self_loop_require_is_warning():
    report = check_participants("v", [
        _module("a.default", provides=[("Vehicle.X",)], requires=[("Vehicle.X",)]),
    ])
    assert any(
        i.rule == "signal_resolution" and i.severity == "warning" and "self-loop" in i.message
        for i in report.issues
    )


def test_unit_underspecified_connection_is_warning():
    # Producer declares a unit, consumer omits it -> under-specified (warning, not silent pass).
    report = check_participants("v", [
        _module("a.default", provides=[Signal("Vehicle.X", "m/s")]),
        _module("b.default", requires=[Signal("Vehicle.X")]),  # no unit
    ])
    assert report.ok  # warning, not error
    assert any(
        i.rule == "unit_consistency" and i.severity == "warning" and "under-specified" in i.message
        for i in report.issues
    )


def test_unit_mismatch_both_declared_is_error():
    # Symmetric: also fires when the producer (not the consumer) carries the odd unit.
    bad = check_participants("v", [
        _module("a.default", provides=[Signal("Vehicle.X", "m/s")]),
        _module("b.default", requires=[Signal("Vehicle.X", "km/h")]),
    ])
    assert "unit_consistency" in _rules_with_errors(bad)


def test_unit_consistency_demo_spec_fails_end_to_end():
    # The shipped powertrain.custom_units swap declares Vehicle.Speed in mph while
    # the plant publishes it in km/h: a real composition that fails on exactly one
    # unit_consistency error (the end-to-end counterpart to the synthetic fixtures).
    comp = load_composition(repo_root() / "spec" / "vehicle.broken_units.yaml")
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)
    report = check_composition(
        comp.name, modules, plant=plant, stimulus_provides=ScenarioStimulus.provides
    )
    assert not report.ok
    unit_errors = [i for i in report.errors if i.rule == "unit_consistency"]
    assert len(unit_errors) == 1
    msg = unit_errors[0].message
    assert "Vehicle.Speed" in msg and "mph" in msg and "km/h" in msg
    # the unit defect is the only error -> a clean single-root-cause demonstration
    assert _rules_with_errors(report) == {"unit_consistency"}


def test_license_non_osi_is_warning_not_error():
    report = check_participants("v", [
        _module("a.default", provides=[("Vehicle.X",)], license="LicenseRef-Proprietary"),
    ])
    assert report.ok  # proprietary swaps are allowed but flagged
    assert any(i.rule == "license" and i.severity == "warning" for i in report.issues)


def test_license_missing_is_error():
    report = check_participants("v", [
        _module("a.default", provides=[("Vehicle.X",)], license=None),
    ])
    assert "license" in _rules_with_errors(report)


def test_license_osi_passes():
    report = check_participants("v", [
        _module("a.default", provides=[("Vehicle.X",)], license="MIT"),
    ])
    assert not any(i.rule == "license" for i in report.issues)


def test_all_default_modules_are_osi_licensed():
    # The shipped reference catalog must be open source (the operator's policy).
    report = _check_spec("vehicle.example.yaml")
    assert not any(i.rule == "license" for i in report.issues)
    modules = [p for p in report.participants if p.is_module]
    assert all(m.license == "Apache-2.0" for m in modules)
