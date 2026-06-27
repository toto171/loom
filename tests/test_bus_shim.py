from loom.bus.shim import ShimBus


def test_publish_read_unit_producer():
    bus = ShimBus()
    bus.publish("Vehicle.Speed", 10.0, unit="km/h", producer="plant")
    assert bus.read("Vehicle.Speed") == 10.0
    assert bus.unit_of("Vehicle.Speed") == "km/h"
    assert bus.producer_of("Vehicle.Speed") == "plant"


def test_read_default_for_unset_path():
    bus = ShimBus()
    assert bus.read("Vehicle.Missing", 42) == 42
    assert bus.read("Vehicle.Missing") is None


def test_snapshot_is_a_copy():
    bus = ShimBus()
    bus.publish("Vehicle.A", 1)
    snap = bus.snapshot()
    snap["Vehicle.A"] = 999
    assert bus.read("Vehicle.A") == 1


def test_paths_are_sorted():
    bus = ShimBus()
    bus.publish("Vehicle.B", 1)
    bus.publish("Vehicle.A", 2)
    assert bus.paths() == ["Vehicle.A", "Vehicle.B"]


def test_republish_preserves_unit_when_omitted():
    bus = ShimBus()
    bus.publish("Vehicle.Speed", 1.0, unit="km/h")
    bus.publish("Vehicle.Speed", 2.0)
    assert bus.read("Vehicle.Speed") == 2.0
    assert bus.unit_of("Vehicle.Speed") == "km/h"
