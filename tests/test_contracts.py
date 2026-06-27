import yaml

from loom.contracts.loader import load_contract, validate_contract_data
from loom.paths import modules_dir


def _bms_contract():
    return yaml.safe_load(
        (modules_dir() / "bms" / "contract.yaml").read_text(encoding="utf-8")
    )


def test_bms_contract_valid_and_parses():
    contract = load_contract(modules_dir() / "bms" / "contract.yaml")
    assert contract.module == "bms.default"
    assert contract.subsystem == "bms"
    assert contract.impl == "default"
    assert contract.safety_level == "ASIL-C"
    assert contract.is_below_safety_line
    assert any(s.path.endswith("StateOfCharge.Current") for s in contract.provides)
    assert any(s.path.endswith("Charging.IsCharging") for s in contract.requires)
    assert contract.failure_modes[0].id == "soc_estimate_drift"


def test_bad_safety_level_fails():
    data = _bms_contract()
    data["safetyLevel"] = "ASIL-Z"
    assert validate_contract_data(data)


def test_non_vehicle_signal_path_fails():
    data = _bms_contract()
    data["signals"]["provides"][0]["path"] = "NotVehicle.Foo"
    assert validate_contract_data(data)


def test_missing_timing_fails():
    data = _bms_contract()
    del data["timing"]
    assert validate_contract_data(data)


def test_unknown_effect_fails():
    data = _bms_contract()
    data["failureModes"][0]["effect"] = "catastrophic"
    assert validate_contract_data(data)
