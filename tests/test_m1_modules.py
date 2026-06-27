"""M1 unit tests: every module contract is valid; stimulus interpolation,
powertrain control direction, and plant dynamics behave as specified."""
from loom.bus.shim import ShimBus
from loom.compose.resolve import resolve_module
from loom.contracts.loader import load_contract
from loom.paths import modules_dir
from loom.plant.loader import load_plant
from loom.sim.stimulus import interpolate_profile

SUBSYSTEMS = ["bms", "powertrain", "adas", "hmi", "body"]

SPEED_SET = "Vehicle.ADAS.CruiseControl.SpeedSet"
SPEED = "Vehicle.Speed"
TORQUE = "Vehicle.Powertrain.ElectricMotor.Torque"


def test_every_module_contract_is_valid_and_matches_subsystem():
    for sub in SUBSYSTEMS:
        contract = load_contract(modules_dir() / sub / "contract.yaml")
        assert contract.subsystem == sub
        assert contract.safety_level in {"QM", "ASIL-A", "ASIL-B", "ASIL-C", "ASIL-D"}
        assert contract.provides  # every module produces at least one signal


def test_safety_line_classification():
    assert load_contract(modules_dir() / "bms" / "contract.yaml").is_below_safety_line  # ASIL-C
    assert load_contract(modules_dir() / "powertrain" / "contract.yaml").is_below_safety_line  # ASIL-B
    assert not load_contract(modules_dir() / "hmi" / "contract.yaml").is_below_safety_line  # QM
    assert not load_contract(modules_dir() / "body" / "contract.yaml").is_below_safety_line  # QM


def test_interpolate_profile_endpoints_clamp_and_midpoint():
    profile = [{"t": 0, "targetSpeedKph": 0}, {"t": 10, "targetSpeedKph": 50}]
    assert interpolate_profile(profile, 0) == 0
    assert interpolate_profile(profile, 10) == 50
    assert interpolate_profile(profile, 5) == 25
    assert interpolate_profile(profile, -1) == 0  # clamp before first point
    assert interpolate_profile(profile, 99) == 50  # clamp after last point
    assert interpolate_profile([], 3) == 0


def test_powertrain_commands_positive_torque_below_setpoint():
    bus = ShimBus()
    pt = resolve_module("powertrain", "default", {}).instance
    bus.publish(SPEED_SET, 50.0)
    bus.publish(SPEED, 0.0)
    pt.step(0.1, 0.1, bus)
    assert bus.read(TORQUE) > 0


def test_powertrain_commands_negative_torque_above_setpoint():
    bus = ShimBus()
    pt = resolve_module("powertrain", "default", {}).instance
    bus.publish(SPEED_SET, 0.0)
    bus.publish(SPEED, 50.0)
    pt.step(0.1, 0.1, bus)
    assert bus.read(TORQUE) < 0


def test_powertrain_torque_is_clamped_to_envelope():
    bus = ShimBus()
    pt = resolve_module("powertrain", "default", {"maxTorqueNm": 100}).instance
    bus.publish(SPEED_SET, 130.0)
    bus.publish(SPEED, 0.0)
    pt.step(0.1, 0.1, bus)
    assert bus.read(TORQUE) == 100.0


def test_plant_accelerates_under_positive_torque():
    bus = ShimBus()
    plant = load_plant("longitudinal", {})
    plant.start(bus)
    bus.publish(TORQUE, 200.0)
    plant.step(0.1, 0.1, bus)
    assert bus.read(SPEED) > 0


def test_plant_stays_stopped_with_no_torque():
    bus = ShimBus()
    plant = load_plant("longitudinal", {})
    plant.start(bus)
    bus.publish(TORQUE, 0.0)
    plant.step(0.1, 0.1, bus)
    assert bus.read(SPEED) == 0.0
