"""M5 assurance + compliance: CycloneDX vehicle SBOM (bill of modules + licenses)
and a GSN assurance-case skeleton whose goals are defeated by real failures."""
import json

from loom.assurance.gsn import build_gsn, render_mermaid
from loom.assurance.sbom import build_vehicle_sbom, sbom_component_count
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.contracts.checker import check_composition
from loom.monitors.engine import Violation
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.sim.stimulus import ScenarioStimulus


def _setup(spec="vehicle.example.yaml"):
    comp = load_composition(repo_root() / "spec" / spec)
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)
    report = check_composition(
        comp.name, modules, plant=plant, stimulus_provides=ScenarioStimulus.provides
    )
    return comp, modules, report


def test_sbom_is_valid_cyclonedx_with_a_component_per_module():
    comp, modules, _ = _setup()
    data = json.loads(build_vehicle_sbom(comp.name, comp.vehicle_class, modules, comp.plant_impl))
    assert data["bomFormat"] == "CycloneDX"
    names = {c["name"] for c in data["components"]}
    assert "bms.default" in names and "plant.longitudinal" in names
    bms = next(c for c in data["components"] if c["name"] == "bms.default")
    assert bms["licenses"][0]["license"]["id"] == "Apache-2.0"
    assert sbom_component_count(modules, comp.plant_impl) == len(modules) + 1


def test_gsn_nominal_run_all_goals_supported():
    comp, modules, report = _setup()
    gsn = build_gsn(comp, modules, report, violations=[])
    ids = {n.id for n in gsn.nodes}
    assert {"G1", "C1", "S1", "G-static", "G-bms"} <= ids
    assert not gsn.defeated  # clean run -> nothing defeated
    mmd = render_mermaid(gsn)
    assert mmd.startswith("flowchart TD") and "G1" in mmd


def test_gsn_goal_defeated_by_monitor_violation_propagates_to_top():
    comp, modules, report = _setup()
    v = Violation(t=1.0, module="bms.default", monitor_id="soc_estimate_drift",
                  kind="failure_detected", message="drift")
    gsn = build_gsn(comp, modules, report, violations=[v])
    g_bms = next(n for n in gsn.nodes if n.id == "G-bms")
    top = next(n for n in gsn.nodes if n.id == "G1")
    assert g_bms.status == "defeated"
    assert top.status == "defeated"  # a defeated sub-goal defeats the top goal
    assert "G-bms" in {n.id for n in gsn.defeated}


def test_swapping_a_module_visibly_changes_the_gsn():
    comp_d, mods_d, rep_d = _setup("vehicle.example.yaml")
    comp_s, mods_s, rep_s = _setup("vehicle.swap_bms.yaml")
    text_default = next(n.text for n in build_gsn(comp_d, mods_d, rep_d, []).nodes if n.id == "G-bms")
    text_swapped = next(n.text for n in build_gsn(comp_s, mods_s, rep_s, []).nodes if n.id == "G-bms")
    assert "bms.default" in text_default
    assert "bms.custom_x" in text_swapped
    assert text_default != text_swapped


def test_gsn_static_failure_defeats_static_and_top_goals():
    # A failing static check defeats G-static, Sn-static, and the top goal G1.
    comp, modules, report = _setup("vehicle.broken.yaml")
    assert not report.ok  # the broken spec genuinely fails the static check
    gsn = build_gsn(comp, modules, report, violations=[])
    by_id = {n.id: n for n in gsn.nodes}
    assert by_id["G-static"].status == "defeated"
    assert by_id["Sn-static"].status == "defeated"
    assert by_id["G1"].status == "defeated"


def test_sbom_is_deterministic_for_identical_inputs():
    comp, modules, _ = _setup()
    a = build_vehicle_sbom(comp.name, comp.vehicle_class, modules, comp.plant_impl)
    b = build_vehicle_sbom(comp.name, comp.vehicle_class, modules, comp.plant_impl)
    assert a == b  # byte-identical: deterministic serial, no wall-clock timestamp


def test_sbom_non_spdx_license_uses_name_field():
    # A proprietary (non-SPDX-id) license falls back to licenses[].license.name.
    class _C:
        module = "vendor.proprietary"
        version = "1.0.0"
        license = "LicenseRef-Proprietary"
        safety_level = "QM"

    class _M:
        subsystem = "vendor"
        impl = "proprietary"
        module_id = "vendor.proprietary"
        contract = _C()

    data = json.loads(build_vehicle_sbom("v", "M1", [_M()]))
    comp = next(c for c in data["components"] if c["name"] == "vendor.proprietary")
    assert comp["licenses"][0]["license"]["name"] == "LicenseRef-Proprietary"
