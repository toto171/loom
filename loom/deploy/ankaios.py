"""Eclipse Ankaios workload manifest for a Loom composition.

Ankaios (https://eclipse-ankaios.github.io) is an automotive workload orchestrator
for HPC/zonal ECUs — the production-grade replacement the design brief anticipates
for the Docker-Compose sketch (``docker-compose.yml``). It consumes a *desired
state*: a set of workloads (containers) with runtimes, agents, and start-up
dependencies. This module renders that desired state from a composition, so the
same vehicle that runs in-process can be deployed onto an Ankaios cluster.

The workload set matches ``docker-compose.yml``: a KUKSA databroker workload plus
one workload per subsystem, each depending on the broker being ``RUNNING`` and
pointed at it via ``KUKSA_ADDRESS``. Wiring uses host networking (rather than
Compose's bridge DNS) so the broker is reachable on the loopback without
provisioning an inter-container network. The signal backbone is unchanged — Ankaios
only changes *who launches the workloads*, which is exactly why the orchestrator
(:class:`loom.orchestrator.ankaios.AnkaiosOrchestrator`) drives the run identically
to the in-process and Compose paths.

Honest scope: this renders an ``ank apply``-*shaped* manifest whose structure and
YAML round-trip are unit-tested; it is NOT validated against a live Ankaios schema,
and the orchestrator's apply path is exercised only against a no-op fake provisioner.
A live deployment additionally needs an Ankaios runtime (``ank-server``/``ank-agent``,
Linux) and built per-module images — the same remaining packaging step noted for
Compose.
"""
from __future__ import annotations

import yaml

ANKAIOS_API_VERSION = "v0.1"
DEFAULT_DATABROKER_IMAGE = "ghcr.io/eclipse-kuksa/kuksa-databroker:latest"


class _AnkaiosDumper(yaml.SafeDumper):
    """Render multi-line strings (the per-workload ``runtimeConfig``) as literal
    block scalars (``|``), the way Ankaios manifests are conventionally written."""


def _str_representer(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_AnkaiosDumper.add_representer(str, _str_representer)


def _runtime_config(image: str, *, command_options=None, command_args=None) -> str:
    """The podman runtime config Ankaios expects as a YAML *string* per workload."""
    cfg: dict = {"image": image}
    if command_options:
        cfg["commandOptions"] = list(command_options)
    if command_args:
        cfg["commandArgs"] = list(command_args)
    return yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False)


def build_ankaios_manifest(
    comp,
    modules,
    *,
    agent: str = "agent_A",
    broker_port: int = 55555,
    databroker_image: str = DEFAULT_DATABROKER_IMAGE,
    module_image=lambda module_id: f"loom/{module_id}:latest",
) -> dict:
    """Return the Ankaios desired-state ``dict`` for a composition.

    One ``databroker`` workload (the KUKSA broker) plus one workload per subsystem
    (named by subsystem), each depending on the broker and addressed at
    ``databroker:<broker_port>``.
    """
    workloads: dict[str, dict] = {
        "databroker": {
            "runtime": "podman",
            "agent": agent,
            "restartPolicy": "ALWAYS",
            # Host networking: the broker binds host:<port> and every workload shares
            # the host network namespace, so the modules reach it on the loopback —
            # no inter-container DNS to provision (podman's default bridge has none),
            # and it matches AnkaiosOrchestrator's own 127.0.0.1:<port> default.
            "runtimeConfig": _runtime_config(
                databroker_image,
                command_options=["--network", "host"],
                command_args=["--insecure", "--port", str(broker_port)],
            ),
        }
    }
    for m in modules:
        # Ankaios workload names must be [A-Za-z0-9_]; subsystem names are, module
        # ids (subsystem.impl) are not — so key by subsystem, tag the image by impl.
        workloads[m.subsystem] = {
            "runtime": "podman",
            "agent": agent,
            "dependencies": {"databroker": "ADD_COND_RUNNING"},
            "runtimeConfig": _runtime_config(
                module_image(m.module_id),
                command_options=["--network", "host", "-e", f"KUKSA_ADDRESS=127.0.0.1:{broker_port}"],
            ),
        }
    # `ank apply` manifests put `workloads` at the top level (the `desiredState`
    # wrapper is the internal CompleteState shape, not the apply-file shape).
    return {"apiVersion": ANKAIOS_API_VERSION, "workloads": workloads}


def dump_ankaios_manifest(comp, modules, **kwargs) -> str:
    """Render :func:`build_ankaios_manifest` as an ``ank apply``-shaped YAML string."""
    return yaml.dump(
        build_ankaios_manifest(comp, modules, **kwargs),
        Dumper=_AnkaiosDumper,
        sort_keys=False,
    )
