# Extending Loom

The framework ([`loom/`](../loom)) loads reference *content* (modules, plants, scenarios)
by name and convention — so the four most common contributions need **no change to the
package**. This guide is the recipe for each. Read [architecture.md](architecture.md) and
[contracts.md](contracts.md) first.

| I want to add… | Touch | Convention |
|---|---|---|
| a subsystem implementation (a swap) | `modules/<subsystem>/` | `IMPLEMENTATIONS` dict + a contract |
| a brand-new subsystem | `modules/<new>/` + a spec | same, plus wire its signals |
| a plant model | `plant/<impl>/` | a `PLANT` class |
| a scenario | `scenarios/<name>.yaml` | drive profile + faults |
| a checker rule | `loom/contracts/checker.py` | a rule fn + a fixture pair |

---

## 1. Add a subsystem implementation (a swap)

Each subsystem lives at `modules/<subsystem>/service.py` and exposes an
**`IMPLEMENTATIONS`** dict mapping an impl name to a [`Module`](../loom/module.py) subclass.
To add a swap, add a class and a registry entry. Example — a second HMI impl
([`modules/hmi/service.py`](../modules/hmi/service.py)):

```python
from loom.module import Module

class HmiDefault(Module):
    subsystem = "hmi"
    impl = "default"

    def start(self, bus):          # optional: seed signals before tick 0
        bus.publish("Vehicle.Cabin.HMI.IsLowBatteryWarningActive", False, producer=self.module_id)

    def step(self, t, dt, bus):     # required: one tick at sim time t, interval dt
        soc = float(bus.read("Vehicle.Powertrain.TractionBattery.StateOfCharge.Current", 100.0) or 100.0)
        bus.publish("Vehicle.Cabin.HMI.IsLowBatteryWarningActive",
                    bool(soc < 20.0), producer=self.module_id)

class HmiCustom(HmiDefault):        # a swap: same interface, different behavior
    subsystem = "hmi"
    impl = "custom"

IMPLEMENTATIONS = {"default": HmiDefault, "custom": HmiCustom}   # <-- the registry
```

Then ship a **contract** alongside it:

- `default` impl → `modules/<subsystem>/contract.yaml`
- any other impl → `modules/<subsystem>/contract.<impl>.yaml`

Select it from a spec with `subsystems.<subsystem>.impl: custom`. The `Module` contract:

- set the class attributes `subsystem` and `impl`;
- implement **`step(self, t, dt, bus)`** — read your `requires`, write your `provides`;
- optionally override `start(bus)` (seed signals) and `stop()` (cleanup);
- `self.params` holds the spec's `subsystems.<key>.params`.

**Mind the safety line.** If your subsystem is below the line (`ASIL-*`), a swap will be
**gated** — the first run with the swap is refused without `--revalidate`. That is working
as designed; see [safety-model.md](safety-model.md). (The biased
[`bms.custom_x`](../modules/bms/contract.custom_x.yaml) is the canonical below-line example;
[`hmi.custom`](../modules/hmi/service.py) is the free above-line one.)

---

## 2. Add a brand-new subsystem

Same as above, in a new `modules/<new>/` directory, **plus**: every signal your module
`requires` must be `provides`d by exactly one producer (another module, the plant, or the
scenario stimulus), or the static checker fails with an unresolved-signal error. Add the
subsystem to a `vehicle.yaml` under `subsystems:` and run `loom check` to confirm the
signal graph closes. Use a real VSS path from the pinned catalog release where one exists.

---

## 3. Add a plant model

Plant implementations live at `plant/<impl>/plant.py` and expose a **`PLANT`** attribute
(a [`Plant`](../loom/plant/base.py) subclass). The plant integrates physics each tick and
publishes ground-truth signals the modules sense; it may also expose a sim-only
ground-truth channel for `truth:` monitor bindings.

```python
from loom.plant.base import Plant

class MyPlant(Plant):
    def step(self, t, dt, bus):
        # read actuator signals (e.g. motor torque), integrate, publish ground truth
        ...

PLANT = MyPlant     # <-- the loader looks for this attribute
```

Select it with `plant.impl: <impl>` in the spec. The existing
[`longitudinal`](../plant/longitudinal/plant.py) (forward-Euler) and
[`motoquant`](../plant/motoquant/plant.py) (RK4 + thermal) publish the **same signal
manifest**, which is exactly why `plant.impl: longitudinal → motoquant` is a drop-in swap
with no module change. Keep that manifest stable for interchangeability. FMU-backed plants
(loaded via FMPy) satisfy the same `Plant` interface.

---

## 4. Add a scenario

Scenarios are plain YAML at `scenarios/<name>.yaml`
([`scenarios/urban_drive.yaml`](../scenarios/urban_drive.yaml)):

```yaml
name: my_drive
description: …
durationS: 20
stepMs: 100                       # sim tick (10 Hz here)
profile:                          # time (s) -> target speed (km/h); the driver tracks this
  - { t: 0,  targetSpeedKph: 0 }
  - { t: 8,  targetSpeedKph: 50 }
  - { t: 20, targetSpeedKph: 0 }
faults:                           # optional fault injection (M3)
  - { kind: dropout, target: Vehicle.Powertrain.TractionBattery.Temperature.Average, fromS: 8, toS: 12 }
```

Fault `kind`s (see [m3-design.md](m3-design.md)): `dropout` (set to `None`), `stuck`
(freeze at `fromS`), `latency` (delay by `latencyMs`), `crash` (freeze all signals a named
`module` produces). List the scenario name under a spec's `scenarios:` and run it with
`loom run <spec> --scenario my_drive`.

---

## 5. Add a static-checker rule

Checker rules live in [`loom/contracts/checker.py`](../loom/contracts/checker.py) and append
results to the `CheckReport`. The project rule (design brief §6, and enforced in review):
**every checker rule ships with a passing *and* a failing fixture.** Add yours to
[`tests/test_m2_checker.py`](../tests/test_m2_checker.py) — a `vehicle.yaml`/contract that
passes and one crafted to trip the new rule with a precise message.

---

## Checklist before you open a PR

- [ ] `loom check <your spec>` passes (signal graph closes, units match, license is open).
- [ ] `loom run <your spec> --scenario <s>` produces a `runs/<id>/` with the expected trace.
- [ ] New rule/feature has a **passing + failing** test (see [CONTRIBUTING](../CONTRIBUTING.md)).
- [ ] `ruff check .` is clean and `pytest` is green.
- [ ] If you added a below-line swap, you exercised the gate (`--revalidate`) in a test.
- [ ] Default/reference content is **open-source licensed** (the checker enforces this).
