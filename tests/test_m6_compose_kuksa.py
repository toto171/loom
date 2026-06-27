"""M6 distributed orchestrator: the KuksaBus VSS adapter (verified against an
injected fake KUKSA client, no live broker) and the ComposeOrchestrator driving
the same scenario over that networked-style bus — equivalent to the in-process run.

The live databroker path (KuksaBus.connect() -> real gRPC) requires a running
KUKSA databroker (Docker), which is not exercised here; the adapter logic and the
orchestrator loop are what these tests pin down.
"""
from kuksa_client.grpc import Datapoint

from loom.bus.kuksa import KuksaBus
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.orchestrator.compose import ComposeOrchestrator
from loom.orchestrator.inprocess import InProcessOrchestrator
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.sim.scenario import load_scenario
from loom.sim.stimulus import ScenarioStimulus
from loom.sim.trace import Trace

SOC = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"


class FakeKuksaClient:
    """In-memory stand-in for kuksa_client.grpc.VSSClient (same set/get surface)."""

    def __init__(self):
        self.store: dict = {}

    def set_current_values(self, mapping):
        self.store.update(mapping)

    def get_current_values(self, paths):
        return {p: self.store.get(p) for p in paths}


def test_kuksa_bus_publish_read_snapshot_against_fake_client():
    bus = KuksaBus(client=FakeKuksaClient())
    bus.publish("Vehicle.Speed", 10.0, unit="km/h", producer="plant")
    assert bus.read("Vehicle.Speed") == 10.0
    assert bus.read("Vehicle.Missing", 42) == 42
    assert bus.unit_of("Vehicle.Speed") == "km/h"
    assert bus.producer_of("Vehicle.Speed") == "plant"
    bus.publish("Vehicle.Powertrain.ElectricMotor.Power", 1234.0)
    snap = bus.snapshot()
    assert snap["Vehicle.Speed"] == 10.0 and snap["Vehicle.Powertrain.ElectricMotor.Power"] == 1234.0
    assert bus.paths() == ["Vehicle.Powertrain.ElectricMotor.Power", "Vehicle.Speed"]


def test_datapoint_value_round_trips():
    assert Datapoint(7.5).value == 7.5


def test_published_none_reads_as_none_like_shimbus():
    # A path published with None reads back as None (not the default) on both buses,
    # so a dropped sensor behaves identically in-process and distributed.
    for bus in (ShimBus(), KuksaBus(client=FakeKuksaClient())):
        bus.publish("Vehicle.T", None)
        assert bus.read("Vehicle.T", 99) is None      # set-to-None -> None, not default
        assert bus.read("Vehicle.Absent", 99) == 99   # genuinely unset -> default


def _run(orchestrator, bus):
    comp = load_composition(repo_root() / "spec" / "vehicle.example.yaml")
    scen = load_scenario("urban_drive")
    plant = load_plant(comp.plant_impl, comp.plant_params)
    modules = resolve_modules(comp)
    trace = Trace()
    result = orchestrator.run(
        modules=[m.instance for m in modules],
        bus=bus, plant=plant, scenario=scen, trace=trace,
        stimulus=ScenarioStimulus(scen),
    )
    return result, trace


def test_compose_orchestrator_over_kuksa_matches_inprocess():
    # Same composition over a (fake-)networked KUKSA bus produces the same outcome
    # as the in-process ShimBus run: SoC drops, speed tracks, identical step count.
    inproc_result, inproc_trace = _run(InProcessOrchestrator(), ShimBus())
    compose_result, compose_trace = _run(
        ComposeOrchestrator(), KuksaBus(client=FakeKuksaClient())
    )

    assert compose_result.orchestrator == "compose"
    assert compose_result.steps == inproc_result.steps
    # SoC drops over the cycle on the networked bus too
    soc_series = compose_trace.series(SOC)
    assert soc_series[0][1] == 80.0 and soc_series[-1][1] < 80.0
    # the two backends agree on the final SoC (bus is interchangeable)
    assert abs(compose_trace.series(SOC)[-1][1] - inproc_trace.series(SOC)[-1][1]) < 1e-9
