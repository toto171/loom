"""Loom — open vehicle composition & virtual-validation framework.

Project vision: compose a vehicle as swappable subsystems behind safety-carrying
contracts, simulate it against a physics plant model, and check composition
compatibility while emitting an assurance-case skeleton and SBOM.

Current build (M0–M6): compose + JSON-Schema validation + the static composition
checker + in-process shim-bus simulation of a five-subsystem vehicle with a
closed cross-module control loop, a longitudinal plant, runtime contract monitors
with fault injection, the safety-line swap gate (below-line ASIL-* swaps require
re-validation), assurance generation (a CycloneDX vehicle SBOM + a GSN
assurance-case skeleton), a higher-fidelity Motoquant plant behind the FMI
boundary, a FastAPI + HTMX web dashboard (compose · run · view), and a distributed
Compose/KUKSA orchestrator (the networked broker behind the same Bus interface).
The full M0–M6 roadmap from HANDOFF.md §8 is implemented.
"""

__version__ = "0.0.1"
