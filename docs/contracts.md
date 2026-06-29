# Contracts & specs — the two core schemas

Loom has exactly two authored file formats, both JSON Schema (written as YAML) under
[`spec/schema/`](../spec/schema):

1. **Composition spec** (`vehicle.yaml`) — *what* vehicle to build.
2. **Contract** (`contract.yaml`) — the safety-carrying interface each module ships.

> Provenance: [design brief](design-brief.md) §5. The schemas are the heart of the system —
> get them right first.

---

## 1. Composition spec — `vehicle.yaml`

Schema: [`spec/schema/composition.schema.json`](../spec/schema/composition.schema.json).
Reference example: [`spec/vehicle.example.yaml`](../spec/vehicle.example.yaml).

```yaml
apiVersion: loom/v0
kind: Vehicle
metadata:
  name: toy-ev-l7            # the gate's trust anchor — see safety-model.md
  vehicleClass: M1           # M1 passenger, N1 LCV, L7 quadricycle, …
plant:
  impl: longitudinal         # which plant/<impl>/plant.py to load (or: motoquant)
  params: { massKg: 1500, wheelRadiusM: 0.31, batteryKwh: 40 }
bus:
  type: vss
  vssRelease: "v4.0"         # COVESA VSS catalog release, pinned for reproducibility
subsystems:
  bms:
    impl: default            # <-- default-or-swap happens here
    params: { cellChemistry: NMC, packSeriesParallel: "96s2p" }
  powertrain: { impl: default }
  adas:
    impl: adas_stub
    params: { odd: { weather: [clear, light_rain], speedMaxKph: 80 } }
  hmi:  { impl: default }
  body: { impl: default }
scenarios:
  - urban_drive
  - sensor_dropout_test
```

| Field | Meaning |
|---|---|
| `metadata.name` | vehicle identity **and the safety baseline key**. Schema-restricted to `^[A-Za-z0-9][A-Za-z0-9 ._-]*$`, ≤64 chars (no path separators — a path-injection defense). |
| `plant.impl` / `plant.params` | which plant model to load and its parameters. |
| `bus.vssRelease` | the VSS catalog release the signal vocabulary is pinned to. |
| `subsystems.<key>.impl` | the implementation to resolve for that subsystem (the swap point). |
| `subsystems.<key>.params` | impl-specific parameters (e.g. an ADAS ODD). |
| `scenarios` | scenario names available to `loom run` (first is the default). |

`resolve_modules` ([`loom/compose/resolve.py`](../loom/compose/resolve.py)) maps each
`subsystems.<key>.impl` to a module under [`modules/`](../modules).

---

## 2. Contract — `contract.yaml`

Schema: [`spec/schema/contract.schema.json`](../spec/schema/contract.schema.json).
Reference: [`modules/bms/contract.yaml`](../modules/bms/contract.yaml), annotated below.

```yaml
apiVersion: loom/v0
kind: Contract
module: bms.default
version: 0.1.0
license: Apache-2.0            # SPDX id, REQUIRED — drives the open-by-default policy
safetyLevel: ASIL-C           # QM | ASIL-A..D — defines which side of the safety line
timing:
  periodMs: 10                # how often it runs
  deadlineMs: 8               # worst-case compute budget within the period
  # resource: hpc-core-0      # OPTIONAL co-location label (see "timing" below)
signals:
  provides:                   # VSS paths this module writes
    - path: Vehicle.Powertrain.TractionBattery.StateOfCharge.Current
      unit: percent
  requires:                   # VSS paths this module reads
    - path: Vehicle.Powertrain.TractionBattery.Charging.IsCharging
    - { path: Vehicle.Powertrain.ElectricMotor.Power, unit: W }
    - { path: Vehicle.Powertrain.TractionBattery.GrossCapacity, unit: kWh }
    - { path: Vehicle.Powertrain.TractionBattery.Temperature.Average, unit: celsius }
      # optional: true        # an unresolved OPTIONAL require is a warning, not an error
failureModes:                 # machine-readable; feed FMEA + runtime monitors
  - id: soc_estimate_drift
    detect: "abs(soc_reported - soc_truth) > 5"   # predicate over bound variables
    effect: degraded
    mitigation: "fall back to coulomb-counting; raise warning signal"
  - id: temp_sensor_fault
    detect: "temp < -20 or temp > 60"   # also trips when temp is unavailable (dropout)
    effect: loss_of_function
    mitigation: "model-based temp estimate; derate charging until the sensor recovers"
bindings:                     # runtime-monitor variable -> source (M3)
  soc_reported: signal:Vehicle.Powertrain.TractionBattery.StateOfCharge.Current
  soc_truth:    truth:soc     # plant ground truth (sim only)
  temp:         signal:Vehicle.Powertrain.TractionBattery.Temperature.Average
assume:                       # preconditions this module needs from the rest of the system
  - "Vehicle.Powertrain.TractionBattery.Temperature.Average between -20 and 60"
guarantee:                    # what this module promises if assumptions hold
  - "soc_reported within 3% of soc_truth under declared ODD"
odd:                          # operational design domain assumptions
  ambientTempC: [-20, 60]
ai:                           # present only for AI/ML modules (ISO 8800 / SOTIF hooks)
  isAiComponent: false
sbomRef: sbom/bms.default.cdx.json   # per-module SBOM, generated under runs/<id>/sbom/
```

### Field reference

| Field | Required | Notes |
|---|---|---|
| `module` | ✓ | `"<subsystem>.<impl>"`, e.g. `bms.default`, `bms.custom_x`. |
| `version` | ✓ | module version (feeds the SBOM). |
| `license` | ✓ | **SPDX id**, validated against the SPDX list. Reference modules are Apache-2.0. |
| `safetyLevel` | ✓ | `QM` (above the line) or `ASIL-A..D` (below). Governs the swap gate. |
| `timing.periodMs` / `deadlineMs` | ✓ | scheduling budget; checked for over-commit per resource. |
| `timing.resource` | — | opt-in co-location label; only modules sharing a label contend (see below). |
| `signals.provides` / `requires` | ✓ | VSS paths with optional `unit`; `requires[].optional` defaults `false`. |
| `failureModes[]` | — | `id` + `detect` predicate + `effect` + `mitigation`. Each becomes a monitor. |
| `bindings` | — | maps predicate variable → `signal:<path>` / `truth:<key>` / `const:<n>`. |
| `assume` / `guarantee` | — | predicates over the composition (prose or evaluable). |
| `odd` | — | operational design domain bounds. |
| `ai.isAiComponent` | — | gate for ISO/PAS 8800 fields on AI modules. |
| `sbomRef` | — | path to this module's SBOM; `loom run`/`loom sbom` generate it at `sbom/<module>.cdx.json` (alongside the aggregate `vehicle.cdx.json`). |

### Predicates and bindings

`failureModes[].detect` and evaluable `guarantee`s are written over symbolic variables
(`temp`, `soc_reported`, `soc_truth`). `bindings` resolves each variable to a source:

- `signal:<VSS path>` — read from the bus (`None` if absent/dropped).
- `truth:<key>` — read from the plant's sim-only ground-truth channel.
- `const:<number>` — a fixed value.

Predicates run in a **whitelisted-AST safe-eval** layer
([`loom/monitors/predicate.py`](../loom/monitors/predicate.py)) — literals, names,
arithmetic, comparisons (incl. chained), boolean ops, and `abs/min/max` only. No `eval`,
no builtins, no attribute access. Evaluation is **three-valued**: a referenced variable
that is `None` (e.g. a dropped sensor) yields an `UNAVAILABLE` sentinel that the engine
treats as a violation rather than crashing on `None < 60`. See [m3-design.md](m3-design.md).

---

## 3. The static checker

[`loom/contracts/checker.py`](../loom/contracts/checker.py) runs before any simulation
(fail-fast) and is also exposed as `loom check`. Rules:

Rule names below are the literal `CheckIssue.rule` identifiers (the `RULES` tuple in
`checker.py`), so they're grep-able in the report and the code:

| Rule | Fails when |
|---|---|
| **`producer_uniqueness`** | a VSS path is provided by more than one producer. |
| **`signal_resolution`** | a (non-optional) `requires` path has no producer. |
| **`unit_consistency`** | a connected provide/require pair declares mismatched units. |
| **`timing`** | the sum of `deadlineMs` on a *shared `resource`* exceeds the period. |
| **`assume_guarantee`** | an assumption references a signal no participant produces. |
| **`license`** | a module's `license` is missing or not an OSI/SPDX id (open-by-default). |

Valid producers are other modules, **the plant**, and **the scenario stimulus**. The
checker emits a `CheckReport` (signal graph + per-rule PASS/FAIL/WARN) rendered by
[`loom/contracts/report.py`](../loom/contracts/report.py).

**Honest scope.** `assume/guarantee` discharge is a *producer-presence proxy* — it confirms
an external participant produces the referenced signal; it does not yet evaluate the
assumption against the producer's `guarantee` predicate (runtime predicate evaluation is
M3). `timing.resource` is opt-in: unlabeled modules are assumed independently scheduled
(a zonal/HPC platform has many cores), and the report says so when no co-location was
declared. See the README's "Contract checker — extensions" section and the per-rule
fixtures in [`tests/test_m2_checker.py`](../tests/test_m2_checker.py).

---

## 4. Open-by-default policy

Every reference/default module ships under an OSI-approved license (all **Apache-2.0**),
declared in its `contract.license` and **enforced by the checker**. The "default-or-swap"
line doubles as an "open default / bring-your-own swap" line: a proprietary swap is allowed
but flagged in the report, so a composition's licensing posture is always visible. This is
a checkable property, not a convention — a default module with a non-open license fails
`loom check`.
