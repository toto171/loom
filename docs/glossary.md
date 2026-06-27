# Glossary

Loom sits at the intersection of automotive standards, functional safety, and simulation.
This is the minimum vocabulary to read the code and docs. Standards links are in the
[design brief](design-brief.md) §12.

## Loom concepts

| Term | Meaning |
|---|---|
| **Subsystem** | a vehicle function (`bms`, `powertrain`, `adas`, `hmi`, `body`). Has one or more implementations. |
| **Implementation / module** | a concrete realization of a subsystem (`bms.default`, `bms.custom_x`). Ships a contract. |
| **Composition spec** (`vehicle.yaml`) | declares which subsystems are present and which impl each uses, plus plant + scenarios. |
| **Contract** (`contract.yaml`) | a module's machine-readable interface **including safety semantics**. See [contracts.md](contracts.md). |
| **Plant** | the physics model (dynamics, battery, thermal) the modules drive and sense. |
| **Scenario** | a time-series stimulus (drive cycle) + optional fault injection. |
| **Safety line** | the boundary between freely-swappable `QM` modules and gated `ASIL-*` modules. |
| **Swap gate** | refuses an unacknowledged below-line implementation swap. See [safety-model.md](safety-model.md). |
| **Lock** | the committed last-validated baseline a vehicle is gated against (`locks/<name>.lock.json`). |
| **Re-validation** | acknowledging + recording a below-line swap (`--revalidate`). |
| **Monitor** | a live predicate (from a `failureMode`/`guarantee`) evaluated each tick during a run. |
| **Fault injection** | scenario-driven signal corruption: `dropout`, `stuck`, `latency`, `crash`. |
| **Ground truth** | sim-only signals the plant exposes so monitors can compare reported vs actual. |
| **Trace** | the per-tick snapshot of every signal, written to `runs/<id>/trace.jsonl`. |

## Standards & external tech

| Term | Meaning |
|---|---|
| **VSS** (COVESA Vehicle Signal Specification) | the standardized dotted-path signal vocabulary (`Vehicle.Speed`). Loom's wire language. |
| **KUKSA** (Eclipse) | a VSS databroker (gRPC); Loom's production signal backbone via `KuksaBus`. |
| **databroker** | the process modules publish/read VSS signals through. |
| **FMI / FMU** (Functional Mock-up Interface / Unit) | a standard co-simulation boundary; the plant plug-in point. |
| **FMPy** | a Python library to load/run FMUs. |
| **Ankaios** (Eclipse) | edge orchestration; the intended Compose replacement behind the `Orchestrator` interface. |
| **SOAFEE / AUTOSAR** | cloud-native mixed-criticality edge architecture / adaptive service-contract concepts. |
| **GSN** (Goal Structuring Notation) | a graphical notation for safety arguments (Goals, Strategies, Solutions). Loom emits a skeleton. |
| **SBOM** (Software Bill of Materials) | the inventory of components + licenses in a build. |
| **CycloneDX** | the SBOM format Loom emits (`vehicle.cdx.json`). |
| **SPDX** | the license-identifier standard used in `contract.license` (e.g. `Apache-2.0`). |

## Functional safety

| Term | Meaning |
|---|---|
| **QM** (Quality Managed) | above the safety line — no ASIL safety-integrity claim; freely swappable. |
| **ASIL-A…D** (Automotive Safety Integrity Level) | below the line; rising integrity/rigor (D highest). From ISO 26262. |
| **ISO 26262** | road-vehicle functional safety (the source of ASIL). |
| **ISO 21448 / SOTIF** | Safety Of The Intended Functionality — hazards from performance limits, not faults. |
| **ISO/PAS 8800** | safety & AI (2024): AI triggering conditions, dataset governance, runtime monitoring. |
| **ODD** (Operational Design Domain) | the conditions a function is designed to operate in (speed, weather, …). |
| **FMEA** | Failure Modes and Effects Analysis; `contract.failureModes` is the machine-readable feed. |
| **Assurance case** | a structured argument (here, GSN) that a system is acceptably safe, with evidence. |
| **UNECE R155 / R156** | type-approval regs for cybersecurity (CSMS) and software updates (SUMS); drive SBOM obligations. |

> Reminder: Loom generates assurance **skeletons** and SBOM **starting points** — never
> certification artifacts. See [design brief](design-brief.md) §11.
