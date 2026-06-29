"""Eclipse Ankaios orchestrator: the deployment-manifest builder and the
AnkaiosOrchestrator driving the same scenario over the networked KUKSA bus —
equivalent to the in-process run, verified against fakes (no Ankaios runtime, no
live broker). Mirrors the Compose/KUKSA verification: Ankaios replaces Compose as
the *workload manager*, but the signal backbone and tick loop are unchanged.
"""
import yaml

from loom.bus.kuksa import KuksaBus
from loom.bus.shim import ShimBus
from loom.compose.loader import load_composition
from loom.compose.resolve import resolve_modules
from loom.deploy.ankaios import build_ankaios_manifest, dump_ankaios_manifest
from loom.orchestrator.ankaios import AnkaiosOrchestrator
from loom.orchestrator.inprocess import InProcessOrchestrator
from loom.paths import repo_root
from loom.plant.loader import load_plant
from loom.sim.scenario import load_scenario
from loom.sim.stimulus import ScenarioStimulus
from loom.sim.trace import Trace

SOC = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"


class FakeKuksaClient:
    def __init__(self):
        self.store: dict = {}

    def set_current_values(self, mapping):
        self.store.update(mapping)

    def get_current_values(self, paths):
        return {p: self.store.get(p) for p in paths}


class FakeAnkaiosProvisioner:
    """Stand-in for an Ankaios control-interface client; records applied states."""

    def __init__(self):
        self.applied: list[dict] = []

    def apply(self, desired_state):
        self.applied.append(desired_state)


def _setup():
    comp = load_composition(repo_root() / "spec" / "vehicle.example.yaml")
    modules = resolve_modules(comp)
    return comp, modules


def _broker_listen_port(wl) -> str:
    args = yaml.safe_load(wl["databroker"]["runtimeConfig"])["commandArgs"]
    return args[args.index("--port") + 1]


def test_manifest_has_databroker_plus_one_workload_per_subsystem():
    comp, modules = _setup()
    man = build_ankaios_manifest(comp, modules)
    assert man["apiVersion"] == "v0.1"
    # `ank apply` shape: workloads at the top level, no internal desiredState wrapper
    assert "desiredState" not in man
    wl = man["workloads"]
    assert set(wl) == {"databroker"} | {m.subsystem for m in modules}
    # every module workload waits for the broker to be running and is pointed at it
    for m in modules:
        w = wl[m.subsystem]
        assert w["runtime"] == "podman"
        assert w["dependencies"] == {"databroker": "ADD_COND_RUNNING"}
        assert f"loom/{m.module_id}:latest" in w["runtimeConfig"]
        assert "KUKSA_ADDRESS=127.0.0.1:55555" in w["runtimeConfig"]
        assert "--network" in w["runtimeConfig"]  # host networking -> broker reachable
    # the broker's listen port is pinned via the parsed --port arg (not a substring)
    assert _broker_listen_port(wl) == "55555"


def test_manifest_yaml_round_trips_and_is_ank_apply_shaped():
    comp, modules = _setup()
    text = dump_ankaios_manifest(comp, modules)
    assert yaml.safe_load(text) == build_ankaios_manifest(comp, modules)
    assert text.startswith("apiVersion: v0.1")
    # workloads is a top-level key (apply shape), with no desiredState wrapper
    assert "\nworkloads:\n" in text
    assert "desiredState" not in text


def test_manifest_honors_custom_agent_and_port():
    comp, modules = _setup()
    man = build_ankaios_manifest(comp, modules, agent="zone_front", broker_port=12345)
    wl = man["workloads"]
    assert all(w["agent"] == "zone_front" for w in wl.values())
    # the broker's actual listen port (--port arg) tracks broker_port independently
    assert _broker_listen_port(wl) == "12345"
    assert "KUKSA_ADDRESS=127.0.0.1:12345" in wl["bms"]["runtimeConfig"]


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


def test_ankaios_orchestrator_over_kuksa_matches_inprocess():
    # Same composition, deployed via (fake) Ankaios and driven over the (fake-)
    # networked KUKSA bus, produces the same outcome as the in-process run.
    inproc_result, inproc_trace = _run(InProcessOrchestrator(), ShimBus())

    comp, modules = _setup()
    provisioner = FakeAnkaiosProvisioner()
    manifest = build_ankaios_manifest(comp, modules)
    orch = AnkaiosOrchestrator(provisioner=provisioner, manifest=manifest)
    ankaios_result, ankaios_trace = _run(orch, KuksaBus(client=FakeKuksaClient()))

    assert ankaios_result.orchestrator == "ankaios"
    assert ankaios_result.steps == inproc_result.steps
    # the orchestrator applied the manifest before driving (provisioning wiring;
    # manifest *correctness* is pinned by the test_manifest_* tests above)
    assert provisioner.applied == [manifest]
    assert "databroker" in provisioner.applied[0]["workloads"]  # a real desired state, not junk
    # SoC drops over the cycle, and the two backends agree on the final value
    soc = ankaios_trace.series(SOC)
    assert soc[0][1] == 80.0 and soc[-1][1] < 80.0
    assert abs(soc[-1][1] - inproc_trace.series(SOC)[-1][1]) < 1e-9


def test_ankaios_orchestrator_runs_without_a_provisioner():
    # Provisioning is optional: with no provisioner/manifest the orchestrator still
    # drives over the bus (the manifest generation is a separate, testable concern).
    _result, trace = _run(
        AnkaiosOrchestrator(), KuksaBus(client=FakeKuksaClient())
    )
    assert trace.series(SOC)[-1][1] < 80.0
