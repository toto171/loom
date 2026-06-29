"""M5 assurance + compliance: CycloneDX vehicle SBOM (bill of modules + licenses)
and a GSN assurance-case skeleton whose goals are defeated by real failures."""
import json

from loom.assurance.gsn import build_gsn, render_mermaid
from loom.assurance.sbom import (
    build_module_sbom,
    build_vehicle_sbom,
    module_sbom_ref,
    sbom_component_count,
    write_vehicle_sboms,
)
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


# --- per-module SBOMs (each contract's sbomRef now resolves to a real file) ---


def test_build_module_sbom_is_a_valid_single_component_cyclonedx():
    _comp, modules, _ = _setup()
    bms = next(m for m in modules if m.module_id == "bms.default")
    data = json.loads(build_module_sbom(bms))
    assert data["bomFormat"] == "CycloneDX" and data["specVersion"] == "1.6"
    root = data["metadata"]["component"]
    assert root["name"] == "bms.default"
    assert root["licenses"][0]["license"]["id"] == "Apache-2.0"
    assert {"name": "loom:safetyLevel", "value": "ASIL-C"} in root["properties"]
    # v0 scope: the module itself, not a transitive dependency tree.
    assert not data.get("components")


def test_build_module_sbom_is_deterministic():
    _comp, modules, _ = _setup()
    bms = next(m for m in modules if m.module_id == "bms.default")
    assert build_module_sbom(bms) == build_module_sbom(bms)  # no wall-clock timestamp


def test_module_sbom_ref_matches_each_shipped_contracts_sbomref():
    _comp, modules, _ = _setup()
    for m in modules:
        # the derived (safe) write path equals the path the contract declares,
        # so the previously-dangling sbomRef now points at a generated artifact.
        assert module_sbom_ref(m.contract) == m.contract.sbom_ref


def _module_of(ref: str) -> str:
    return ref.removeprefix("sbom/").removesuffix(".cdx.json")


def test_write_vehicle_sboms_emits_vehicle_plus_one_per_module(tmp_path):
    comp, modules, _ = _setup()
    result = write_vehicle_sboms(tmp_path, comp.name, comp.vehicle_class, modules, comp.plant_impl)
    assert (tmp_path / "vehicle.cdx.json").exists()
    assert len(result["modules"]) == len(modules)
    for ref in result["modules"]:
        data = json.loads((tmp_path / ref).read_text(encoding="utf-8"))
        assert data["bomFormat"] == "CycloneDX"
        # the file at sbom/<module>.cdx.json must actually be THAT module's SBOM
        # (pins the file<->module pairing of the write loop), and v0 single-component scope.
        assert data["metadata"]["component"]["name"] == _module_of(ref)
        assert not data.get("components")


def test_execute_run_emits_per_module_sboms_resolving_every_sbomref(tmp_path, monkeypatch):
    import loom.run as run_mod

    monkeypatch.setattr(run_mod, "runs_dir", lambda: tmp_path / "runs")
    monkeypatch.setattr(run_mod, "locks_dir", lambda: tmp_path / "locks")
    outcome = run_mod.execute_run(
        repo_root() / "spec" / "vehicle.example.yaml", "urban_drive"
    )
    refs = outcome.summary["assurance"]["moduleSboms"]
    # anchor to the YAML-declared sbomRef (not the production derivation) so this
    # independently proves every contract's sbomRef is the path that gets generated.
    assert set(refs) == {m.contract.sbom_ref for m in outcome.modules}
    for m in outcome.modules:
        # the contract's declared sbomRef resolves to a real artifact in the run dir
        assert (outcome.run_dir / m.contract.sbom_ref).exists()


def test_module_sbom_ref_and_write_are_independent_of_a_declared_sbomref():
    # The derived-vs-declared reconciliation must not depend on sbomRef being present:
    # a contract that omits it (sbom_ref=None) still gets a derived path + a real file.
    from loom.contracts.model import Contract

    class _M:
        contract = Contract(
            module="vendor.noref", version="1.0.0", license="Apache-2.0",
            safety_level="QM", period_ms=10.0, deadline_ms=10.0,
        )

    m = _M()
    assert m.contract.sbom_ref is None
    assert module_sbom_ref(m.contract) == "sbom/vendor.noref.cdx.json"
    data = json.loads(build_module_sbom(m))
    assert data["metadata"]["component"]["name"] == "vendor.noref"


def test_loom_sbom_cli_writes_vehicle_and_per_module_sboms(tmp_path):
    from typer.testing import CliRunner

    from loom.cli import app

    spec = str(repo_root() / "spec" / "vehicle.example.yaml")
    result = CliRunner().invoke(app, ["sbom", spec, "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "vehicle.cdx.json").exists()
    bms = tmp_path / "sbom" / "bms.default.cdx.json"
    assert bms.exists()
    data = json.loads((tmp_path / "vehicle.cdx.json").read_text(encoding="utf-8"))
    assert data["bomFormat"] == "CycloneDX"
    # the per-module file is the right module's SBOM, not a stray copy
    assert json.loads(bms.read_text(encoding="utf-8"))["metadata"]["component"]["name"] == "bms.default"
