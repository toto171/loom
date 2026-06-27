# M3 design — runtime monitors + fault injection

**Goal (HANDOFF §8 M3):** translate `failureModes` + `guarantee`s into live
monitors; implement fault injection (dropout, stuck, latency, crash); the
`sensor_dropout_test` scenario.
**Acceptance:** injecting a battery-temp sensor dropout trips the `bms` monitor
and the violation appears in the run report with a timestamp.

---

## 1. Safe-eval predicate layer (`loom/monitors/predicate.py`)

HANDOFF §6: "small safe-eval expression layer: restricted Python expressions over
named signals; no `eval` of arbitrary code." Implemented as a whitelisted-AST
evaluator (Python `ast`), supporting only:

- literals (numbers, strings, `True`/`False`/`None`);
- names (resolved from a `variables` dict);
- arithmetic `+ - * / %`, unary `-`, comparisons (incl. chained `a < b < c`),
  boolean `and/or/not`, `is`/`is not`;
- a tiny function whitelist: `abs`, `min`, `max`.

Anything else (calls to other names, attribute access, subscripts, comprehensions,
lambdas) raises `PredicateError`. No `eval`/`exec`, no builtins, no `__`.

`evaluate(expr, variables) -> bool`. If any referenced variable is **unavailable**
(`None` — e.g. a dropped-out sensor), evaluation short-circuits to a special
`Unavailable` result that the engine treats as a violation ("required signal
unavailable"), rather than crashing on `None < 60`.

## 2. Variable bindings (contract addition)

`failureModes[].detect` and `guarantee`s are written over symbolic variable names
(e.g. `temp`, `soc_reported`, `soc_truth`). A contract gains an optional
`bindings` map (variable name → source):

```yaml
bindings:
  temp:         signal:Vehicle.Powertrain.TractionBattery.Temperature.Average
  soc_reported: signal:Vehicle.Powertrain.TractionBattery.StateOfCharge.Current
  soc_truth:    truth:stateOfCharge      # plant ground truth (sim only)
```

Source schemes:
- `signal:<VSS path>` — read from the bus (None if absent/dropped).
- `truth:<key>` — read from the plant's ground-truth channel (sim only).
- `const:<number>` — a fixed value.

Schema: add `bindings` (object, propertyNames = identifier, values = string) to
`contract.schema.json`. The static checker (M2) already validates `detect`
strings exist; M3 adds: every name used in a monitored `detect` has a binding
(else a contract-load warning).

## 3. Monitors (`loom/monitors/engine.py`)

From each module contract, build monitors:
- one per `failureMode` — trips when `detect` evaluates true (the failure
  condition holds) **or** a referenced signal is unavailable;
- one per `guarantee` that is expressed as an evaluable predicate (guarantees in
  prose are skipped with a logged note — honest scoping).

`MonitorEngine.evaluate(t, bus, truth) -> list[Violation]` runs every monitor each
tick. `Violation(t, module, monitor_id, kind, message)`. Collected into the run
report (`runs/<id>/violations.jsonl` + a summary section).

## 4. Fault injection (`loom/sim/faults.py`)

`FaultInjector` applies `scenario.faults` to the bus each tick, **after** the
plant publishes its sensors and **before** the modules step + monitors evaluate —
so the corrupted (e.g. dropped) sensor is what the consuming modules (this tick,
via last-good-hold) and the monitors see. Tick order becomes:

`stimulus → plant.step → faults.apply → modules.step → monitors.evaluate → record`

Fault kinds (`{kind, target, fromS, toS, ...}`):
- **dropout** — within `[fromS, toS]`, set `target` to `None` (sensor offline).
- **stuck** — hold the value captured at `fromS` (frozen sensor).
- **latency** — publish the value from `latencyMs` ago (delay buffer).
- **crash** — freeze *all* signals a named `module` produces (process died).

## 5. Plant ground truth

The plant publishes a sim-only ground-truth channel (e.g. `stateOfCharge`,
integrated independently from the BMS estimate) for `truth:` bindings, so monitors
like `soc_estimate_drift` (`abs(soc_reported - soc_truth) > 5`) are evaluable. In
nominal runs the BMS estimate equals truth (no drift), so that monitor stays
green; it exists to be tripped by a faulty/biased BMS swap later.

## 6. Acceptance demo

`scenarios/sensor_dropout_test.yaml` already injects a `dropout` on
`Vehicle.Powertrain.TractionBattery.Temperature.Average` over `t ∈ [8, 12]`. The
BMS gains a `temp_sensor_fault` failure mode (`detect: temp < -20 or temp > 60`,
binding `temp → Temperature.Average`). During the dropout the temp variable is
`None` → the monitor reports "required signal unavailable" → a violation with a
timestamp lands in the run report. `loom run spec/vehicle.example.yaml --scenario
sensor_dropout_test` shows it.

## 7. Files
- `loom/monitors/predicate.py` (safe-eval), `loom/monitors/engine.py` (monitors).
- `loom/sim/faults.py` (injector) + orchestrator wiring (new tick step).
- `loom/contracts/{model,loader}.py` + `contract.schema.json` — `bindings`.
- `plant/longitudinal/plant.py` — ground-truth SoC channel.
- `modules/bms/contract.yaml` — `bindings` + `temp_sensor_fault` failure mode.
- run report: `violations.jsonl` + summary; CLI prints a violations count.
- tests: predicate eval (safe + rejected), each fault kind, the dropout→violation
  acceptance, "no violations on a clean run".

## Known simplifications (honest scoping)
- Guarantees in prose are not evaluated (only predicate-form ones are).
- `latency` uses a per-tick delay buffer (integer tick granularity).
- Ground truth is sim-only and Loom-namespaced, not a real VSS signal.
