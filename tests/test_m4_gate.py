"""M4 safety-line swap gate: below-line (ASIL-*) swaps are refused without
re-validation; QM swaps are free; the custom_x BMS trips the drift monitor."""
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_module, resolve_modules
from loom.monitors.engine import MonitorEngine
from loom.orchestrator.inprocess import InProcessOrchestrator
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.safety.gate import current_config, detect_swaps, gate, load_lock, write_lock
from loom.sim.faults import FaultInjector
from loom.sim.scenario import load_scenario
from loom.sim.stimulus import ScenarioStimulus
from loom.sim.trace import Trace


class _Mod:
    """Minimal stand-in for a resolved module."""

    def __init__(self, subsystem, impl, safety):
        self.subsystem = subsystem
        self.impl = impl
        self.contract = type("C", (), {"safety_level": safety})()


def test_no_lock_means_no_swaps():
    cur = current_config([_Mod("bms", "default", "ASIL-C")])
    assert detect_swaps(cur, None) == []


def test_no_change_is_no_swap():
    lock = {"subsystems": {"bms": {"impl": "default", "safetyLevel": "ASIL-C"}}}
    cur = current_config([_Mod("bms", "default", "ASIL-C")])
    assert detect_swaps(cur, lock) == []


def test_below_line_swap_refused_without_revalidate_allowed_with():
    lock = {"subsystems": {"bms": {"impl": "default", "safetyLevel": "ASIL-C"}}}
    cur = current_config([_Mod("bms", "custom_x", "ASIL-C")])
    swaps = detect_swaps(cur, lock)
    assert len(swaps) == 1 and swaps[0].below_line

    refused = gate(swaps, revalidate=False)
    assert not refused.allowed and "bms" in refused.refused_reason

    allowed = gate(swaps, revalidate=True)
    assert allowed.allowed and allowed.gated_swaps


def test_qm_swap_is_free():
    lock = {"subsystems": {"hmi": {"impl": "default", "safetyLevel": "QM"}}}
    cur = current_config([_Mod("hmi", "custom", "QM")])
    swaps = detect_swaps(cur, lock)
    assert swaps and not swaps[0].below_line
    assert gate(swaps, revalidate=False).allowed


def test_replacing_an_asil_module_with_qm_is_still_gated():
    lock = {"subsystems": {"bms": {"impl": "default", "safetyLevel": "ASIL-C"}}}
    cur = current_config([_Mod("bms", "qm_variant", "QM")])
    swaps = detect_swaps(cur, lock)
    assert swaps[0].below_line  # old side was ASIL -> still crosses the line
    assert not gate(swaps, revalidate=False).allowed


def test_adding_an_asil_subsystem_is_gated():
    # Introducing a brand-new below-line subsystem (not just replacing one) gates.
    lock = {"subsystems": {"hmi": {"impl": "default", "safetyLevel": "QM"}}}
    cur = current_config([_Mod("hmi", "default", "QM"), _Mod("brakes", "bbw", "ASIL-D")])
    swaps = detect_swaps(cur, lock)
    added = [s for s in swaps if s.subsystem == "brakes"]
    assert added and added[0].below_line
    assert not gate(swaps, revalidate=False).allowed


def test_removing_an_asil_subsystem_is_gated():
    lock = {
        "subsystems": {
            "hmi": {"impl": "default", "safetyLevel": "QM"},
            "brakes": {"impl": "bbw", "safetyLevel": "ASIL-D"},
        }
    }
    cur = current_config([_Mod("hmi", "default", "QM")])  # brakes dropped
    swaps = detect_swaps(cur, lock)
    removed = [s for s in swaps if s.subsystem == "brakes"]
    assert removed and removed[0].below_line
    assert not gate(swaps, revalidate=False).allowed


def test_malformed_lock_missing_safety_level_fails_safe():
    # An old lock entry lacking safetyLevel must gate (fail-safe), not slip through.
    lock = {"subsystems": {"bms": {"impl": "default"}}}  # no safetyLevel
    cur = current_config([_Mod("bms", "custom_x", "QM")])
    swaps = detect_swaps(cur, lock)
    assert swaps[0].below_line
    assert not gate(swaps, revalidate=False).allowed


def test_hmi_custom_qm_swap_is_free_end_to_end():
    # The real custom QM impl resolves and a QM swap is allowed without --revalidate.
    resolved = resolve_module("hmi", "custom", {})
    assert resolved.module_id == "hmi.custom"
    assert not resolved.contract.is_below_safety_line  # QM
    lock = {"subsystems": {"hmi": {"impl": "default", "safetyLevel": "QM"}}}
    swaps = detect_swaps(current_config([resolved]), lock)
    assert swaps and not swaps[0].below_line
    assert gate(swaps, revalidate=False).allowed


def test_lock_round_trip(tmp_path):
    path = tmp_path / "toy.lock.json"
    cur = current_config([_Mod("bms", "default", "ASIL-C"), _Mod("hmi", "default", "QM")])
    write_lock(path, "toy", cur)
    loaded = load_lock(path)
    assert loaded["vehicle"] == "toy"
    assert loaded["subsystems"]["bms"]["impl"] == "default"
    assert detect_swaps(cur, loaded) == []


def test_custom_x_bms_resolves_with_its_own_contract():
    resolved = resolve_module("bms", "custom_x", {})
    assert resolved.module_id == "bms.custom_x"
    assert resolved.contract.module == "bms.custom_x"
    assert resolved.contract.is_below_safety_line  # ASIL-C


def test_swapped_biased_bms_trips_drift_monitor():
    # The whole point of the gate: the custom_x BMS over-reports SoC, so its
    # estimate drifts from plant ground truth and the runtime monitor catches it.
    comp = load_composition(repo_root() / "spec" / "vehicle.swap_bms.yaml")
    scen = load_scenario("urban_drive")
    bus = ShimBus()
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)
    result = InProcessOrchestrator().run(
        modules=[m.instance for m in modules],
        bus=bus,
        plant=plant,
        scenario=scen,
        trace=Trace(),
        stimulus=ScenarioStimulus(scen),
        faults=FaultInjector(scen.faults),
        monitors=MonitorEngine.from_modules(modules),
    )
    drift = [v for v in result.violations if v.monitor_id == "soc_estimate_drift"]
    assert drift, "expected the biased custom_x BMS to trip soc_estimate_drift"
    assert all(v.module == "bms.custom_x" for v in drift)
