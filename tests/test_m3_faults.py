"""M3 fault injection: dropout/stuck within windows, latency delay, crash set."""
from loom.bus.shim import ShimBus
from loom.sim.faults import FaultInjector
from loom.sim.scenario import Fault


def test_dropout_sets_none_only_within_window():
    bus = ShimBus()
    fi = FaultInjector([Fault(kind="dropout", target="Vehicle.T", from_s=1.0, to_s=2.0)])

    bus.publish("Vehicle.T", 25)
    fi.apply(0.5, bus)
    assert bus.read("Vehicle.T") == 25  # before window

    bus.publish("Vehicle.T", 25)
    fi.apply(1.5, bus)
    assert bus.read("Vehicle.T") is None  # in window -> dropped

    bus.publish("Vehicle.T", 25)
    fi.apply(2.5, bus)
    assert bus.read("Vehicle.T") == 25  # after window


def test_stuck_holds_value_captured_at_window_entry():
    bus = ShimBus()
    fi = FaultInjector([Fault(kind="stuck", target="Vehicle.T", from_s=1.0, to_s=3.0)])

    bus.publish("Vehicle.T", 10)
    fi.apply(1.0, bus)
    assert bus.read("Vehicle.T") == 10

    bus.publish("Vehicle.T", 99)
    fi.apply(2.0, bus)
    assert bus.read("Vehicle.T") == 10  # frozen at the entry value


def test_latency_publishes_delayed_value():
    bus = ShimBus()
    fi = FaultInjector([Fault(kind="latency", target="Vehicle.T", from_s=0.0, to_s=10.0, raw={"delayTicks": 1})])
    # delay=1: first tick has no history (real value passes), then each tick lags by one.
    for value, expected in [(1, 1), (2, 1), (3, 2), (4, 3)]:
        bus.publish("Vehicle.T", value)
        fi.apply(value, bus)  # use value as a stand-in tick time
        assert bus.read("Vehicle.T") == expected


def test_crashed_modules_within_window():
    fi = FaultInjector([Fault(kind="crash", from_s=1.0, to_s=2.0, raw={"module": "adas.adas_stub"})])
    assert fi.crashed_modules(1.5) == {"adas.adas_stub"}
    assert fi.crashed_modules(0.5) == set()


def test_dropout_active_at_t0():
    # A fault whose window opens at t=0 must be injected on the initial tick.
    bus = ShimBus()
    bus.publish("Vehicle.T", 25)
    fi = FaultInjector([Fault(kind="dropout", target="Vehicle.T", from_s=0.0, to_s=1.0)])
    fi.apply(0.0, bus)
    assert bus.read("Vehicle.T") is None
