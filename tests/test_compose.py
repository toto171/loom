import pytest
import yaml

from loom.compose.loader import load_composition, validate_composition_data
from loom.errors import ValidationError
from loom.paths import repo_root


def _load(name):
    return yaml.safe_load((repo_root() / "spec" / name).read_text(encoding="utf-8"))


def test_example_spec_is_valid():
    assert validate_composition_data(_load("vehicle.example.yaml")) == []


def test_m0_spec_is_valid():
    assert validate_composition_data(_load("vehicle.m0.yaml")) == []


def test_missing_subsystems_fails():
    data = _load("vehicle.example.yaml")
    del data["subsystems"]
    errors = validate_composition_data(data)
    assert errors and any("subsystems" in e for e in errors)


def test_wrong_api_version_fails():
    data = _load("vehicle.example.yaml")
    data["apiVersion"] = "loom/v999"
    assert validate_composition_data(data)


def test_subsystem_missing_impl_fails():
    data = _load("vehicle.m0.yaml")
    data["subsystems"]["bms"] = {"params": {}}
    assert validate_composition_data(data)


def test_load_parses_subsystem_selections():
    comp = load_composition(repo_root() / "spec" / "vehicle.example.yaml")
    assert comp.name == "toy-ev-l7"
    assert comp.plant_impl == "longitudinal"
    assert comp.subsystem("bms").impl == "default"
    assert comp.subsystem("adas").impl == "adas_stub"
    assert comp.scenarios[0] == "urban_drive"


def test_malformed_yaml_raises_validation_error(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("apiVersion: loom/v0\n  : : [unbalanced", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_composition(p)


def test_path_injection_vehicle_name_rejected_by_schema():
    data = _load("vehicle.example.yaml")
    data["metadata"]["name"] = "../../tmp/x"
    assert validate_composition_data(data)  # rejected (no path separators allowed)
