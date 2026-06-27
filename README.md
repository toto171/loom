# Loom

**Open vehicle composition & virtual-validation framework.**

Declare a vehicle as a composition of swappable subsystems (BMS, powertrain,
ADAS, HMI, body…), each behind a **contract that carries safety semantics**, run
the composed vehicle against a **physics plant model in simulation**, and
**generate the assurance case + SBOM as you compose**. Above the safety line,
modules mix-and-match freely; below it, swaps trigger re-validation gates.

The novel core is the **contract layer**: existing buses (VSS, SOME/IP, DDS)
carry the bytes but not the *safety semantics*. Loom makes those semantics
first-class and machine-checkable.

> This is **development and validation tooling**, not a certified in-vehicle
> production runtime. See [`HANDOFF.md`](HANDOFF.md) §11.

---

## Status — M0–M6 complete (compose · check · gate · simulate · monitor · assure · dashboard)

The full M0–M6 roadmap is implemented and green. The end-to-end loop runs:

```
compose -> validate (schema) -> check (static contract) -> gate (safety-line swap) -> run (modules + plant + driver + faults + monitors) -> trace + report + violations + SBOM + GSN assurance
```

What works today:

- Composition spec + contract **JSON Schemas** and typed loaders.
- In-process **VSS shim broker** behind an abstract `Bus`.
- **Five reference modules** with real, schema-valid contracts: `bms` (ASIL-C),
  `powertrain` (ASIL-B), `adas` (ASIL-B stub), `hmi` (QM), `body` (QM).
- A **longitudinal plant** with real forward-Euler dynamics behind the FMI-style
  `Plant` boundary, and a **scenario driver** that drives a cruise set-speed.
- A closed **cross-module control loop** over VSS signals: the driver sets a
  target speed → powertrain commands motor torque → plant integrates speed +
  electrical power → BMS integrates State-of-Charge (with regen recovery).
- The **static composition checker** (`loom check`): producer-uniqueness,
  signal-resolution, unit-consistency, timing (per co-located resource),
  assume/guarantee discharge (by an *external* producer), and an **open-source
  license** policy — emitting a **composition report** (signal graph + per-rule
  results). `loom run` runs it fail-fast before bringing the sim up.
- **Open-by-default policy**: every reference/default module ships under an
  OSI-approved license (all Apache-2.0), declared in its contract and enforced by
  the checker. The "default-or-swap" line is also an "open default / bring-your-own
  swap" line — proprietary swaps are allowed but flagged.
- **Runtime contract monitors + fault injection** (M3): each module's
  `failureModes.detect` predicate becomes a live monitor (via a sandboxed
  safe-eval layer + variable→signal/truth/const bindings), evaluated against the
  bus + plant ground truth each tick; the scenario can inject `dropout` / `stuck`
  / `latency` / `crash` faults. Violations land in the run report with timestamps.
- **Safety-line swap gate** (M4): a vehicle's last-validated configuration is
  recorded in a lock; swapping a **below-line (ASIL-*)** implementation is refused
  unless `--revalidate` is passed (which records a re-validation entry). Above-line
  (QM) swaps are free. A second BMS impl (`bms.custom_x`) demonstrates it.
- **Assurance generation** (M5): every run emits a **CycloneDX vehicle SBOM**
  (bill of modules + declared licenses) and a **GSN assurance-case skeleton**
  (YAML + rendered Mermaid) built from the contracts + check results + runtime
  outcomes. A goal is **defeated** when its evidence fails — so the biased
  `bms.custom_x` swap that trips the drift monitor automatically defeats its
  contract goal and the top-level safety goal.
- An **in-process orchestrator** that drives a scenario and records a trace.
- `loom validate` / `loom check` / `loom run`, plus a pytest suite (111 tests,
  incl. automated M0–M5 acceptance and per-rule M2 fixtures).

Verified acceptance:
- **M1**: `loom run spec/vehicle.example.yaml --scenario urban_drive` drives a
  full drive cycle — **speed tracks the cycle** (mean error < 2 km/h) and **SoC
  drops** (80.0 → 79.96%).
- **M2**: `loom check spec/vehicle.broken.yaml` fails with a precise unresolved-
  signal message; `loom check spec/vehicle.example.yaml` passes and emits the report.
- **M3**: `loom run spec/vehicle.example.yaml --scenario sensor_dropout_test`
  trips the BMS `temp_sensor_fault` monitor at **[8–12 s]** (battery-temp sensor
  dropout); a clean run reports no violations.
- **M4**: after a baseline run, `loom run spec/vehicle.swap_bms.yaml` is **refused**
  (ASIL-C BMS swap) until `--revalidate` is passed; the re-validated `bms.custom_x`
  then trips the `soc_estimate_drift` monitor — the gate + monitor catching a real
  miscalibration introduced by the swap.
- **M5**: every run writes `runs/<id>/vehicle.cdx.json` + `assurance.gsn.yaml` +
  `assurance.gsn.mmd`; the biased-BMS swap defeats the `G-bms` and top-level `G1`
  assurance goals — the assurance case visibly changes with the composition.
- **M6 plant swap**: `loom run spec/vehicle.motoquant.yaml` switches only
  `plant.impl: longitudinal → motoquant` — a higher-fidelity engine (RK4 + a
  thermal battery model, so temperature varies) runs the same scenario with no
  module change, proving the FMI plant plug-in point.
- **M6 dashboard**: `uvicorn dashboard.app:app` — browse the catalog, assemble a
  composition, launch a run, and view its report / GSN assurance / SBOM. It goes
  through the same `execute_run` pipeline, so it inherits the safety-line gate.
- **M6 distributed orchestrator**: `ComposeOrchestrator` drives the sim over a
  networked **KUKSA databroker** (`KuksaBus`, the same `Bus` interface as the
  shim) — verified equivalent to the in-process run against an injected client.
  The live databroker path uses the repo's `docker-compose.yml` (needs Docker).

Design notes: [`docs/m1-design.md`](docs/m1-design.md),
[`docs/m3-design.md`](docs/m3-design.md), [`docs/m5-design.md`](docs/m5-design.md).

---

## Quickstart

Requires Python 3.12.

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on POSIX
pip install -e ".[dev]"

loom validate spec/vehicle.example.yaml                      # schema validation -> OK
loom check spec/vehicle.example.yaml                          # static contract check + report -> OK
loom check spec/vehicle.broken.yaml                           # deliberately broken -> precise failure
loom run spec/vehicle.example.yaml --scenario urban_drive          # 5 modules; speed tracks cycle, SoC drops
loom run spec/vehicle.example.yaml --scenario sensor_dropout_test  # temp dropout trips a BMS monitor
loom run spec/vehicle.swap_bms.yaml                                # below-line BMS swap -> refused without --revalidate
loom run spec/vehicle.swap_hmi.yaml                                # above-line (QM) HMI swap -> free, no gate
loom run spec/vehicle.motoquant.yaml                              # M6: swap to the higher-fidelity plant (no module change)
# each run also writes runs/<id>/vehicle.cdx.json (SBOM) + assurance.gsn.{yaml,mmd}
pip install -e ".[dashboard]" && uvicorn dashboard.app:app        # M6 web dashboard at http://127.0.0.1:8000
pytest                                                            # 123 tests (M0–M6)
```

`loom run` writes `runs/<id>/trace.jsonl` (per-tick signal snapshots) and
`runs/<id>/run.json` (summary incl. which signals changed).

---

## Design decision: orchestrator ↔ broker pairing

The handoff lists both an in-process VSS *shim* broker and *Docker Compose*
orchestration for M0. Those don't compose directly: an in-process broker can
only be shared by modules in the **same process**, while Compose runs each module
as a separate container. So Loom pairs them deliberately, both behind the same
`Orchestrator` interface (honoring the "≥2 implementations from day one"
principle):

| Orchestrator | Broker | Status |
|---|---|---|
| `InProcessOrchestrator` | in-process `ShimBus` | default — deterministic, no container runtime |
| `ComposeOrchestrator` | networked KUKSA databroker (`KuksaBus`) | **M6** — implemented (shares the tick loop), verified equivalent against an injected client; the live databroker path needs Docker |

Both reuse the same tick loop (`loom/orchestrator/_loop.py`), so a distributed run
behaves identically to an in-process one. `docker-compose.yml` brings up the KUKSA
databroker; full per-module containerization is the remaining production step.
Eclipse Ankaios can later replace Compose behind the same interface.

---

## Contract checker — extensions beyond HANDOFF §5.2

The checker implements the five §5.2 rules and adds three deliberate, documented
extensions to the contract schema:

- **`timing.resource`** — opt-in co-location label. The §5.2 utilization rule
  ("sum of deadlines on a shared resource ≤ period") only contends modules that
  declare the same resource; unlabeled modules are assumed independently scheduled
  (a zonal/central-HPC platform has many cores). The report notes when no
  co-location was declared, so a reader knows the utilization half was inert.
- **`signal.optional`** — a defaultable input. An unresolved *optional* require is
  a warning, not an error (used only for the plant's torque input, so a vehicle
  with no powertrain is a valid stationary composition). No module contract uses it.
- **`license`** (SPDX, required) — drives the open-by-default policy above.

**Scope honesty:** `assume_guarantee` discharges an assumption by checking that an
*external* participant produces the referenced signal (a producer-presence proxy);
it does **not** match the assumption against the producer's `guarantee` predicate —
runtime predicate evaluation is M3. Of the three §8 breakage classes, only
*unresolved-signal* is demonstrable end-to-end via a `vehicle.yaml`
([`spec/vehicle.broken.yaml`](spec/vehicle.broken.yaml)); *unit-mismatch* and
*timing-overcommit* are proven by unit fixtures (`tests/test_m2_checker.py`) and
become spec-demonstrable once the M4 swap demo introduces alternate module impls.

---

## Safety-line gate — the lock & its trust model

The gate compares the current composition against a vehicle's **last-validated
configuration**, recorded in a lock at `locks/<metadata.name>.lock.json`. The lock
is **committed, versioned state** (a run input that travels with the repo) — *not*
gitignored runtime, so a routine `rm -rf runs/` can't silently reset the safety
baseline. Writes are atomic.

Trust model (honest about the boundaries — this is dev/validation tooling, not a
certified runtime):

- **Trust anchor is `metadata.name`.** Two specs sharing a name are compared
  against the same baseline (intended — that's how the swap demo works); renaming
  the vehicle starts a fresh baseline.
- **Trust-on-first-use.** The first run of a vehicle establishes its baseline; if
  it contains below-line (ASIL-*) modules, the run prints a baseline notice.
  Establish the baseline from a known-good spec.
- **Swaps gate on the union of subsystems**: replacing an impl, *and* adding or
  removing a below-line subsystem, all require `--revalidate`. A malformed lock
  entry (missing safety level) fails safe (gates).

---

## Layout

See [`HANDOFF.md`](HANDOFF.md) §7 for the full repository map and §2 for the core
concepts (subsystem, implementation, contract, plant, scenario, safety line,
assurance case). The two core schemas live in `spec/schema/`.
