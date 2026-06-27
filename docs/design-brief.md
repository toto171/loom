# Loom — Founding Design Brief (the original handoff)

**Open Vehicle Composition & Virtual-Validation Framework**
*(working codename "Loom")*

> ℹ️ **Status of this document.** This is the *founding design brief* that scoped Loom
> (M0–M6). It is preserved as a historical / rationale document — the "why now," the
> standards landscape, the schema intent, and the per-milestone acceptance criteria.
> **It is not the current source of truth for the as-built system** — for that, start at the
> [README](../README.md) and the living docs under [`docs/`](README.md)
> ([architecture](architecture.md), [contracts](contracts.md), [safety model](safety-model.md)).
> Throughout the code, comments cite this document as **"HANDOFF §N"**; the section numbers
> below are unchanged so those citations still resolve here. The repository map in §7 is the
> *initial plan*; see [architecture.md](architecture.md) for the as-built layout.

> A framework where you declare a vehicle as a composition of swappable subsystems
> (autopilot, ADAS, BMS, powertrain, HMI, body…), each behind a **contract that carries
> safety semantics**, run the composed vehicle against a **physics plant model in
> simulation**, and **generate the assurance case + SBOM as you compose**. Above the
> safety line, modules are freely mix-and-match; below it, swaps trigger re-validation gates.

This document is written for an implementing agent (Claude Code) and assumes no access to
the conversation that produced it. It is self-contained.

---

## 0. TL;DR — what we are building

A developer-facing tool that turns the idea "pick your subsystems, default-or-swap" into a
working **compose → simulate → check** loop:

1. **Compose** — author a `vehicle.yaml` selecting subsystems and choosing `impl: default`
   or a custom implementation for each. Subsystems are wired together over a standardized
   signal vocabulary (COVESA **VSS**).
2. **Simulate** — the selected subsystem modules run as containerized services against a
   **vehicle-dynamics plant model** plus virtual buses, driving through scenarios, with
   fault injection.
3. **Check** — a **contract layer** verifies, statically and at runtime, that the composed
   modules are actually compatible in the dimensions that matter (signals, timing budgets,
   failure modes, ASIL/QM level, ODD assumptions) — and emits a **composition safety report**,
   a **CycloneDX SBOM**, and a **GSN assurance-case skeleton**.

The novel core is the **contract layer**: existing buses (SOME/IP, DDS, VSS) carry the bytes
but not the *safety semantics*. Loom makes those semantics first-class and machine-checkable.
This is the part that does not exist as open software today, and it is the part that makes a
"default-or-swap" vehicle framework actually safe rather than just convenient.

This is **development and validation tooling**, not a certified in-vehicle production runtime.
See §11 ("What this is NOT").

---

## 1. Why this, and why now (the research that drove the design)

The 5–10 year (≈2031–2036) automotive-software landscape is converging on a small number of
forces. Loom is positioned at the intersection of the ones that are (a) real, (b) under-served
by open tooling, and (c) buildable in pure software.

- **Centralized compute is the substrate.** ECU counts drop from 100+ to <10 by ~2030 on
  zonal + central-HPC topologies. The differentiator becomes the software stack and the
  abstraction layer, not the wiring.
- **The "AI-defined vehicle."** ADAS is moving AV 1.0 (modular) → AV 2.0 (end-to-end learned)
  → AV 3.0 (Vision-Language-Action foundation models). Software's share of automotive R&D is
  projected to roughly triple (≈21% → ≈58%) by 2035.
- **A real vehicle abstraction layer is landing.** AUTOSAR, COVESA, Eclipse SDV, and SOAFEE
  declared a "collaboration of collaborations" (CES 2024). COVESA **VSS** is the emerging
  semantic signal vocabulary; Eclipse **KUKSA** abstracts vehicle signals to VSS so functions
  run across heterogeneous hardware. Build ON this, do not reinvent it.
- **In-vehicle software is going cloud-native + orchestrated** (Eclipse **Ankaios**, SOAFEE
  microservices on HPC, CI/CD).
- **Virtual-first / "shift-left" is becoming mandatory.** 600M+ lines of code, hundreds of
  suppliers; the answer is virtual ECUs + full-vehicle digital twins with physics plant
  models *before hardware exists*. The proprietary incumbents (Synopsys eDT, Siemens PAVE360,
  Vector) are expensive and SoC-vendor-locked. **Open gap.**
- **Continuous certification is the great unsolved problem.** OTA breaks static type approval.
  The literature converges on dynamic / through-life **safety cases**, variability-aware
  assurance (fleet-as-software-product-line), and **runtime monitors derived from the safety
  argument**. Loom's contract + assurance layer is a concrete take on this.
- **AI gets its own safety regime.** ISO/PAS 8800 (Dec 2024) extends SOTIF (ISO 21448) to AI
  — AI triggering conditions, dataset governance, scenario/statistical validation, runtime
  monitoring. You cannot V-model a neural net; modules carrying AI need these fields.
- **Security + supply-chain compliance are now law.** UNECE R155/R156 (CSMS/SUMS) for type
  approval; China GB 44495:2024 (eff. Jan 2026); EU Cyber Resilience Act (obligations from
  Dec 2027); R155 extending to L-category (motorcycles) from Dec 2027. **SBOMs and continuous
  vulnerability management are operational requirements.** Loom emits SBOMs by construction.

**The gap Loom fills:** lots of standards + open pieces (VSS, KUKSA, Ankaios, SOAFEE, FMI) and
lots of closed proprietary digital-twin tooling — but **no open, composition-first framework
that ties them together and makes safety semantics a first-class, checkable contract across
swappable subsystems.** That is the wedge.

---

## 2. Core concepts (the mental model)

- **Subsystem** — a vehicle function (e.g. `bms`, `powertrain`, `adas`, `hmi`, `body`,
  `chassis`). Each has one or more **implementations** (`default` + zero or more custom).
- **Implementation (module)** — a containerized service that realizes a subsystem's behavior,
  communicates over VSS signals, and ships a **contract** + an **SBOM**.
- **Composition Spec** (`vehicle.yaml`) — declares which subsystems are present and which
  implementation each uses (default-or-swap), plus global parameters (the plant model, the
  scenario set, the bus config).
- **Contract** — the machine-readable interface of a module **including safety semantics**:
  provided/required VSS signals, timing budget (period + deadline), declared failure modes,
  assume/guarantee predicates, `safety_level` (QM / ASIL-A…D), ODD assumptions, and (for AI
  modules) AI-triggering-condition + dataset-governance metadata.
- **Plant model** — the physics of the vehicle (dynamics, powertrain, battery, environment)
  that the software modules drive and sense. **This is the Motoquant plug-in point.** v0 ships
  a simple longitudinal+bicycle model; a high-fidelity engine (RK4 / Pacejka) drops in via the
  FMI boundary.
- **Scenario** — a time-series stimulus (drive cycle, sensor inputs, environment) + optional
  **fault injection** (signal dropouts, stuck values, latency spikes, module crash).
- **Safety line** — the boundary between freely-swappable modules (`QM`, e.g. infotainment)
  and re-validation-gated modules (`ASIL-*`, e.g. ADAS/BMS/brake-by-wire). Encoded per module
  via `safety_level`; the checker enforces gates on below-line swaps.
- **Assurance case** — a GSN (Goal Structuring Notation) argument that the composed vehicle is
  acceptably safe, assembled from module contracts + check results, and **recomposed when a
  module is swapped**.

---

## 3. Scope — v0

**In scope for v0** (prove the whole loop end-to-end on a deliberately small "toy" vehicle —
breadth over fidelity):

- Composition Spec parser + JSON-Schema validation.
- Contract model + JSON-Schema + **static compatibility checker** (signals, timing, safety
  level, ODD).
- A small **catalog of reference/default modules**: `bms`, `powertrain`, `adas_stub`, `hmi`,
  `body` (each a real Python service with a real contract; behavior can be simple).
- **Signal backbone** on VSS via KUKSA databroker (or a thin VSS shim if KUKSA integration is
  slow to stand up — see §6).
- A **plant model**: longitudinal vehicle dynamics + a simple battery model, exposed behind an
  FMI-style boundary so Motoquant can replace it later.
- A **scenario runner** (drive cycle) with **fault injection** and trace recording.
- **Runtime contract monitors** (flag violations during a sim run).
- A **swap demo**: replace `bms.default` with `bms.custom_x` via `vehicle.yaml`, re-run, show
  the below-line **re-validation gate** trigger.
- **Outputs**: composition graph, static-check report, runtime-violation report, **CycloneDX
  SBOM**, **GSN assurance-case skeleton**, all from one `loom run`.
- CLI (`loom`) driving the whole thing; `docker compose` for orchestration.

**Out of scope for v0** (explicitly deferred — note them, do not build them yet):

- Real neural ADAS / real perception. `adas_stub` is a placeholder that exercises the contract
  machinery (timing, failure modes, ODD), not a real driver.
- High-fidelity vehicle dynamics (that is Motoquant, integrated in a later milestone).
- Ankaios / production orchestration (Docker Compose is fine for v0; keep the orchestration
  boundary clean so Ankaios can slot in).
- Real hardware / HIL / real vECU instruction-accurate models.
- Web dashboard until M6.
- Any claim of certification or production-readiness.

---

## 4. Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │                 loom CLI                     │
                         │   compose · validate · run · report          │
                         └───────────────┬─────────────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                 │                                │
        ▼                                 ▼                                ▼
┌───────────────┐              ┌────────────────────┐            ┌──────────────────┐
│  COMPOSE      │              │   CONTRACTS        │            │   ASSURANCE      │
│  parse+valid. │─ contracts ─▶│  static checker    │─ results ─▶│  GSN + SBOM gen  │
│  vehicle.yaml │              │  (signal/timing/   │            │  safety report   │
└──────┬────────┘              │   safety/ODD)      │            └──────────────────┘
       │ selected modules      └─────────┬──────────┘
       │                                 │ runtime monitors
       ▼                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              SIM RUNTIME (docker compose)                          │
│                                                                                    │
│   ┌──────────┐   ┌────────────┐   ┌────────────┐   ┌────────┐   ┌────────┐         │
│   │   bms    │   │ powertrain │   │ adas_stub  │   │  hmi   │   │  body  │  ...     │
│   └────┬─────┘   └─────┬──────┘   └─────┬──────┘   └───┬────┘   └───┬────┘         │
│        │               │                │              │            │              │
│        └───────────────┴────────VSS signals (KUKSA databroker)──────┴──────────┐   │
│                                         │                                       │   │
│                                         ▼                                       │   │
│                        ┌────────────────────────────────┐                      │   │
│                        │   PLANT MODEL (FMI boundary)    │◀── scenario + faults │   │
│                        │   v0: longitudinal + battery    │                      │   │
│                        │   later: Motoquant (RK4/Pacejka)│── trace recorder ────┘   │
│                        └────────────────────────────────┘                          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Data flow per run:** `loom run vehicle.yaml --scenario urban_drive`
1. parse + validate composition → resolve module set
2. static contract check (fail fast on incompatibility or ungated below-line swap)
3. bring up broker + plant + selected modules via compose
4. drive the scenario (with fault injection), record traces, run runtime monitors
5. tear down; assemble composition safety report + SBOM + GSN skeleton into `runs/<id>/`

---

## 5. The two core schemas

These are the heart of the system. Get them right first.

### 5.1 Composition Spec — `spec/vehicle.example.yaml`

```yaml
apiVersion: loom/v0
kind: Vehicle
metadata:
  name: toy-ev-l7
  vehicleClass: M1          # M1 passenger, N1 LCV, L7 quadricycle, etc.
plant:
  impl: longitudinal        # v0 default; later: motoquant
  params:
    massKg: 1500
    wheelRadiusM: 0.31
    batteryKwh: 40
bus:
  type: vss
  vssRelease: "v4.0"        # COVESA VSS catalog release pinned for reproducibility
subsystems:
  bms:
    impl: default           # <-- default-or-swap happens here
    params: { cellChemistry: NMC, packSeriesParallel: "96s2p" }
  powertrain:
    impl: default
  adas:
    impl: adas_stub
    params: { odd: { weather: [clear, light_rain], speedMaxKph: 80 } }
  hmi:
    impl: default
  body:
    impl: default
scenarios:
  - urban_drive
  - sensor_dropout_test
```

### 5.2 Contract — shipped by each module as `contract.yaml`

```yaml
apiVersion: loom/v0
kind: Contract
module: bms.default
version: 0.1.0
safetyLevel: ASIL-C          # QM | ASIL-A | ASIL-B | ASIL-C | ASIL-D  (defines the safety line)
timing:
  periodMs: 10               # how often it runs
  deadlineMs: 8              # worst-case compute budget within the period
signals:
  provides:                  # VSS paths this module writes
    - path: Vehicle.Powertrain.TractionBattery.StateOfCharge.Current
      unit: percent
    - path: Vehicle.Powertrain.TractionBattery.Temperature.Average
      unit: celsius
  requires:                  # VSS paths this module reads
    - path: Vehicle.Powertrain.TractionBattery.Charging.IsCharging
failureModes:                # declared, machine-readable; feeds FMEA + monitors
    - id: soc_estimate_drift
      detect: "abs(soc_reported - soc_truth) > 5"   # checked against plant in sim
      effect: degraded
      mitigation: "fall back to coulomb-counting; raise warning signal"
assume:                      # preconditions this module needs from the rest of the system
    - "Vehicle.Powertrain.TractionBattery.Temperature.Average between -20 and 60"
guarantee:                   # what this module promises if assumptions hold
    - "soc_reported within 3% of soc_truth under declared ODD"
odd:                         # operational design domain assumptions
    ambientTempC: [-20, 60]
ai:                          # present only for AI/ML modules (ISO 8800 / SOTIF hooks)
  isAiComponent: false
sbomRef: sbom/bms.default.cdx.json   # CycloneDX SBOM for this module
```

**Static checker rules (v0 minimum):**
- every `requires` signal is `provides`d by exactly one other module (no unresolved / no
  conflicting producers);
- units match on connected signals;
- timing composes (sum of deadlines on a shared resource ≤ period; flag overcommit);
- `assume`/`guarantee` predicates are well-formed and assumptions are discharged by some
  module's guarantee or the plant;
- **safety-line gate**: if a swap replaces a module whose `safetyLevel` is below QM
  (i.e. any ASIL-*), require a `--revalidate` acknowledgement + a recorded re-validation
  entry; refuse silently-swapped below-line modules.

**Runtime monitors (v0 minimum):** translate each `failureMode.detect` and each `guarantee`
into a live predicate evaluated against recorded signals + plant ground truth during the run;
log violations with timestamps to the run report.

---

## 6. Tech stack

Chosen to (a) be Python-centric so the Motoquant physics core integrates cleanly, (b) match
the operator's existing comfort zone (Python, Docker Compose, HTMX/Alpine, Postgres), and
(c) build on open automotive standards rather than reinvent them.

| Concern | Choice | Notes |
|---|---|---|
| Language | **Python 3.12** | core, modules, plant, CLI |
| Signal backbone | **COVESA VSS** + **Eclipse KUKSA databroker** | VSS = interface vocabulary; KUKSA = the broker (gRPC). Pin a VSS release. |
| Fallback broker | thin in-process **VSS shim** | if KUKSA integration blocks M0/M1, ship a minimal pub/sub VSS broker behind the same interface and swap to KUKSA later. Keep the broker boundary abstract. |
| Co-simulation boundary | **FMI 3.0 / FMU** via **FMPy** | plant models are FMUs (or native-Python implementing the same interface) so Motoquant slots in as a standard component |
| Containers / orchestration | **Docker + Docker Compose** | v0. Keep an `Orchestrator` abstraction so **Eclipse Ankaios** can replace Compose later |
| Schemas | **JSON Schema** (authored as YAML) | validate composition + contracts; use `jsonschema` |
| SBOM | **CycloneDX** via `cyclonedx-python-lib` | one SBOM per module + an aggregate vehicle SBOM |
| Assurance case | **GSN** emitted as YAML + rendered to **Mermaid**/Graphviz | machine-readable first, human-rendered second |
| Contracts predicates | small safe-eval expression layer | restricted Python expressions over named signals; no `eval` of arbitrary code |
| Testing | **pytest** | every checker rule gets a unit test with a passing + failing fixture |
| CLI | **Typer** (or argparse) | `loom compose|validate|run|report` |
| Web dashboard (M6) | **FastAPI** or **Django 5** + **HTMX** + **Alpine.js** | matches operator's stack; visualize composition graph, run scenarios, browse reports |
| Persistence (M6) | **PostgreSQL 16** | run history, module catalog; v0 can use the filesystem (`runs/<id>/`) |

**Standards to align with (so output is credible, not bespoke):** COVESA VSS; Eclipse KUKSA;
FMI 3.0; CycloneDX (or SPDX) for SBOM; GSN Community Standard for assurance; AUTOSAR Adaptive
SOA concepts (service contracts); SOAFEE patterns (cloud-native, mixed-criticality); and the
safety-field vocabulary of ISO 26262 (ASIL), ISO 21448 (SOTIF / ODD / triggering conditions),
ISO/PAS 8800 (AI triggering conditions, dataset governance), and UNECE R155/R156 (update +
SBOM metadata).

---

## 7. Repository structure

```
loom/
├── README.md
├── docs/design-brief.md            # this file (was HANDOFF.md at the repo root)
├── pyproject.toml
├── docker-compose.yml
├── spec/
│   ├── vehicle.example.yaml
│   └── schema/
│       ├── composition.schema.json
│       └── contract.schema.json
├── loom/                           # the package
│   ├── cli.py                      # `loom` entrypoint
│   ├── compose/                    # parse + validate composition spec, resolve module set
│   ├── contracts/                  # contract model, loader, static checker
│   ├── monitors/                   # runtime contract monitors
│   ├── assurance/                  # GSN builder + CycloneDX SBOM aggregation + safety report
│   ├── sim/                        # scenario runner, fault injection, trace recorder
│   ├── bus/                        # broker abstraction (KUKSA impl + shim impl)
│   ├── plant/                      # plant model abstraction + FMI loader
│   └── orchestrator/              # Compose impl behind an Orchestrator interface
├── modules/                        # reference/default subsystem implementations
│   ├── bms/        { service.py, contract.yaml, Dockerfile, sbom/ }
│   ├── powertrain/ { ... }
│   ├── adas_stub/  { ... }
│   ├── hmi/        { ... }
│   └── body/       { ... }
├── plant/
│   └── longitudinal/               # v0 default plant (FMU or native-Python)
├── scenarios/
│   ├── urban_drive.yaml
│   └── sensor_dropout_test.yaml
├── runs/                           # generated; one dir per run (gitignored)
├── dashboard/                      # M6 web UI
└── tests/
```

---

## 8. Build plan — milestones

Each milestone ends with a runnable artifact and explicit acceptance criteria. Do them in
order; do not start a milestone until the previous one's acceptance criteria pass.

**M0 — Scaffold + schemas + one signal**
- repo scaffold, `pyproject.toml`, `loom` CLI skeleton, both JSON Schemas, broker abstraction
  with the in-process VSS **shim**, one trivial module that writes one VSS signal.
- *Accept:* `loom validate spec/vehicle.example.yaml` passes; `loom run` brings up the shim +
  one module and one VSS signal is observed changing in the trace.

**M1 — Reference modules + plant + scenario end-to-end**
- implement `bms`, `powertrain`, `adas_stub`, `hmi`, `body` as containerized services with real
  contracts; longitudinal plant model behind the FMI boundary; `urban_drive` scenario; trace
  recorder.
- *Accept:* `loom run spec/vehicle.example.yaml --scenario urban_drive` drives a full drive
  cycle; SoC drops, speed tracks the cycle, traces land in `runs/<id>/`.

**M2 — Static contract checker + composition report**
- implement all §5.2 static rules with unit tests (passing + failing fixtures each); generate
  a human-readable composition report (graph + check results).
- *Accept:* a deliberately broken `vehicle.yaml` (unit mismatch / unresolved signal / timing
  overcommit) fails validation with a precise message; a good one passes and emits the report.

**M3 — Runtime monitors + fault injection**
- translate `failureModes` + `guarantee`s into live monitors; implement fault injection
  (dropout, stuck, latency, crash); `sensor_dropout_test` scenario.
- *Accept:* injecting a battery-temp sensor dropout trips the `bms` monitor and the violation
  appears in the run report with a timestamp.

**M4 — Swap demo + safety-line gate**
- add a second BMS impl (`bms.custom_x`); implement the below-line re-validation gate.
- *Accept:* editing `vehicle.yaml` to `bms.impl: custom_x` and re-running **refuses** without
  `--revalidate` (because BMS is ASIL-*), and **proceeds + records a re-validation entry** with
  it. Swapping an above-line (`QM`) module needs no gate.

**M5 — Assurance + compliance generation**
- aggregate per-module CycloneDX SBOMs into a vehicle SBOM; build a GSN assurance-case skeleton
  from contracts + check results; render to Mermaid.
- *Accept:* one `loom run` produces `vehicle.cdx.json`, `assurance.gsn.yaml`, and a rendered
  GSN diagram in `runs/<id>/`; swapping a module visibly changes the assurance skeleton.

**M6 — Web dashboard + Motoquant plant**
- FastAPI/Django + HTMX/Alpine UI to browse the catalog, edit a composition, launch runs, and
  view reports/graphs; integrate the high-fidelity plant model (Motoquant) behind the existing
  FMI boundary.
- *Accept:* a composition can be assembled and run from the browser; switching `plant.impl`
  from `longitudinal` to `motoquant` runs the same scenario through the high-fidelity engine
  with no other code change.

---

## 9. First tasks for Claude Code (start here, in this order)

1. Initialize the repo per §7. Set up `pyproject.toml` (Python 3.12, deps: `typer`,
   `jsonschema`, `pyyaml`, `fmpy`, `cyclonedx-python-lib`, `pytest`). Add `.gitignore`
   (include `runs/`).
2. Write `spec/schema/composition.schema.json` and `spec/schema/contract.schema.json` from
   §5.1 and §5.2. Add `spec/vehicle.example.yaml`.
3. Implement `loom/compose/` (load + JSON-Schema-validate the composition spec; resolve the
   selected module set) and `loom/contracts/` (load + validate a `contract.yaml`).
4. Implement the `loom/bus/` abstraction with the **in-process VSS shim** first (a typed
   pub/sub over VSS paths). Define the interface so a KUKSA implementation can replace it.
5. Implement `loom/cli.py` with `loom validate` wired to steps 2–3.
6. Build the smallest possible `modules/bms/` (one service writing one signal) + its
   `contract.yaml`, and the `loom/orchestrator/` Compose runner, to hit **M0 acceptance**.
7. Only then proceed to M1.

Keep every abstraction boundary (`bus`, `plant`, `orchestrator`) clean and interface-first —
the whole point of Loom is swappability, so the framework's own internals must be swappable too
(shim→KUKSA, Compose→Ankaios, longitudinal→Motoquant).

---

## 10. Design principles (non-negotiables)

1. **Build on open standards; do not reinvent.** VSS for signals, FMI for plant, CycloneDX for
   SBOM, GSN for assurance, AUTOSAR/SOAFEE concepts for service contracts.
2. **The contract layer is the product.** Anyone can wire services on a bus; the value is the
   machine-checkable *safety semantics* across module boundaries. Invest there.
3. **Simulation-first.** The framework is a virtual vehicle you compose and validate before any
   hardware exists. The physics plant model is the differentiator (and the Motoquant tie-in).
4. **The safety line is explicit and enforced.** Above-line (`QM`) modules mix-and-match freely;
   below-line (`ASIL-*`) swaps are gated and recorded. Never let a below-line module swap pass
   silently.
5. **Everything reproducible.** Pin the VSS release, module versions, scenario seeds. A run is a
   function of its inputs.
6. **Interface-first internals.** `bus`, `plant`, `orchestrator` are abstractions with ≥2
   implementations in mind from day one.
7. **Honest scoping.** Generate *skeletons* of assurance cases and *starting points* for SBOM /
   TARA — never imply they constitute certification (see §11).

---

## 11. What this is NOT (read before overclaiming)

- **Not a certified in-vehicle production runtime.** Loom is dev + validation tooling. Shipping
  a real vehicle still requires a responsible integrator (OEM/Tier-1) to own the integrated
  safety case, type approval, and liability. Loom *helps build and argue* that case; it does
  not *constitute* it.
- **Not a real autonomous-driving stack.** `adas_stub` exercises the contract machinery; it is
  not a driver. A real neural/VLA driver would be integrated later as one module among many,
  with its ISO 8800 / SOTIF fields populated.
- **Not a replacement for HIL / physical testing.** Shift-left complements, not replaces,
  hardware-in-the-loop and on-road validation.
- **Not a marketplace.** Sourcing modules (à la SDVerse) is a separate concern; Loom is about
  composing + validating what you have, not buying it.

---

## 12. References (standards, projects, key sources)

**Standards / specs**
- COVESA Vehicle Signal Specification (VSS) — https://covesa.global/project/vehicle-signal-specification/
- Eclipse KUKSA (VSS databroker) — https://github.com/eclipse-kuksa
- Eclipse Ankaios (edge orchestration) — https://eclipse-ankaios.github.io/
- SOAFEE (Scalable Open Architecture for Embedded Edge) — https://www.soafee.io/
- AUTOSAR Adaptive Platform — https://www.autosar.org/
- FMI (Functional Mock-up Interface) 3.0 — https://fmi-standard.org/  ·  FMPy — https://github.com/CATIA-Systems/FMPy
- CycloneDX SBOM — https://cyclonedx.org/  ·  SPDX — https://spdx.dev/
- GSN (Goal Structuring Notation) Community Standard — https://scsc.uk/gsn
- ISO 26262 (functional safety / ASIL); ISO 21448 (SOTIF); ISO/PAS 8800 (safety & AI, 2024);
  ISO/SAE 21434 (cybersecurity engineering)
- UNECE WP.29 R155 (CSMS) & R156 (SUMS) — https://unece.org/transport/vehicle-regulations
- EU Cyber Resilience Act (obligations from Dec 2027); China GB 44495:2024

**Landscape / trend sources (for context, not implementation)**
- McKinsey — next-gen E/E architecture with zonal compute; the rise of edge AI in automotive
- IBM Automotive 2035 (software R&D share ≈21% → ≈58%)
- Eclipse SDV / "collaboration of collaborations" (AUTOSAR + COVESA + Eclipse SDV + SOAFEE, CES 2024)
- AWS/NVIDIA AV 1.0 → 2.0 → 3.0 (VLA) framing; Alpamayo reasoning VLA model
- Synopsys eDT, Siemens PAVE360, Vayavya Labs — shift-left / vECU / vehicle-level digital twins
- SDVerse — B2B automotive software marketplace (the sourcing layer, distinct from Loom)
- Eclipse "Open AD Kit" / Autoware (open AD, first SOAFEE blueprint)

---

*End of handoff. Build M0 first; do not skip the schemas.*
