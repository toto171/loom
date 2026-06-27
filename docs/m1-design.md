# M1 design — reference modules + plant + scenario end-to-end

**Goal (HANDOFF §8 M1):** implement `bms`, `powertrain`, `adas_stub`, `hmi`,
`body` as real modules with real contracts; a longitudinal plant behind the FMI
boundary; the `urban_drive` scenario; trace recorder.
**Acceptance:** `loom run spec/vehicle.example.yaml --scenario urban_drive`
drives a full drive cycle; **SoC drops, speed tracks the cycle**, traces land in
`runs/<id>/`.

Principle: *breadth over fidelity* (HANDOFF §3). The point of M1 is a coherent
**cross-module loop over VSS signals**, not accurate vehicle physics.

---

## Integration contract — one producer per VSS path

The M2 static checker will require every `requires` signal to be `provides`d by
**exactly one** producer (HANDOFF §5.2). Plant and the scenario stimulus count as
valid producers (HANDOFF §5.2: assumptions discharged "by some module's guarantee
**or the plant**"). So the signal map below assigns each path a single producer.

| VSS path | unit | producer | consumers |
|---|---|---|---|
| `Vehicle.ADAS.CruiseControl.SpeedSet` | km/h | **scenario** (driver) | powertrain |
| `Vehicle.ADAS.CruiseControl.IsActive` | bool | **scenario** (driver) | adas |
| `Vehicle.Powertrain.TractionBattery.Charging.IsCharging` | bool | **scenario** (env) | bms |
| `Vehicle.Powertrain.ElectricMotor.Torque` | Nm | **powertrain** | plant |
| `Vehicle.Speed` | km/h | **plant** | powertrain, adas, body |
| `Vehicle.Powertrain.ElectricMotor.Power` | W | **plant** | bms |
| `Vehicle.Powertrain.TractionBattery.GrossCapacity` | kWh | **plant** | bms |
| `Vehicle.Powertrain.TractionBattery.Temperature.Average` | celsius | **plant** | bms |
| `Vehicle.Powertrain.TractionBattery.StateOfCharge.Current` | percent | **bms** | hmi |
| `Vehicle.ADAS.LaneKeepingAssist.IsEngaged` | bool | **adas** | (none yet) |
| `Vehicle.Cabin.HMI.IsLowBatteryWarningActive` | bool | **hmi** | (none) |
| `Vehicle.Body.Lights.Brake.IsActive` | bool | **body** | (none) |

(`adas` is the subsystem key; its M1 implementation is `adas_stub`. Pack capacity
`GrossCapacity` is published once by the plant as ground truth and consumed by the
BMS — single source of truth for SoC integration.)

`scenario` and `plant` are non-module producers; every module-`requires` path is
produced by exactly one of {another module, plant, scenario}. No path has two
producers → the composition will satisfy the M2 producer-uniqueness rule.

---

## The control loop

A driver (the scenario) sets a target speed; the powertrain is a P-controller
that commands motor torque; the plant integrates longitudinal dynamics and
publishes ground-truth speed + electrical power; the BMS integrates battery
energy from that power.

**Tick order (per sim step):** `scenario stimulus → plant.step → modules.step → record`.
This is the M0 order (plant before modules) plus a stimulus prelude — minimal
change. Inherent one-tick lag: powertrain's torque at tick *t* is consumed by the
plant at tick *t+1* (unavoidable in a single fixed-order pass; acceptable for M1).

### Scenario stimulus (`loom/sim/stimulus.py`)
Linear-interpolate `profile` `targetSpeedKph` at time *t*; publish
`CruiseControl.SpeedSet` + `IsActive=true` + `Charging.IsCharging=false`
(producer label `scenario`). Fault injection (M3) will hook the same prelude.

### Plant (`plant/longitudinal/plant.py`, real dynamics)
- Read `ElectricMotor.Torque` (default 0).
- `F_traction = Torque · gearRatio / wheelRadius`.
- `F_resist = 0.5·ρ·CdA·v² + Crr·m·g` (opposes motion; only while v>0).
- `a = (F_traction − sign(v)·F_resist)/m`; integrate `v += a·dt`; clamp `v ≥ 0`.
- Publish `Vehicle.Speed` (km/h) and `ElectricMotor.Power` (W) =
  `F_traction · v_avg` (midpoint speed over the step) adjusted by drivetrain
  efficiency (motoring `/η` vs regen `·η`).
- Publish `GrossCapacity` (kWh) once at start as battery ground truth (consumed
  by the BMS — single source of truth for pack capacity).
- Constants: ρ=1.2, CdA=0.66, Crr=0.01, g=9.81, gearRatio=9, η=0.9, Tmax bound
  enforced by powertrain. Defaults overridable via plant params.

### Powertrain (`modules/powertrain/`, P-controller), ASIL-B
- Read `CruiseControl.SpeedSet`, `Vehicle.Speed`.
- `error = set_mps − v_mps`; `Torque = clamp(Kp·error, −Tmax, +Tmax)`
  (Kp≈200 Nm·s/m, Tmax≈300 Nm; negative torque = regen/brake).
- Publish `ElectricMotor.Torque`.

### BMS (`modules/bms/`, evolve M0 → M1), ASIL-C
- Read `ElectricMotor.Power`, `Charging.IsCharging`, `GrossCapacity`,
  `Temperature.Average` (battery thermal sensor — the plant is the ground-truth
  producer, so the BMS's temperature assumption is discharged externally).
- `energy_J = P_elec · dt` (+ small constant aux load); `SoC −= energy_J /
  (GrossCapacity·3.6e6) · 100`; clamp [0,100]. Charging flips the sign.
- Publish `StateOfCharge.Current`. Hold last good temperature on a sensor dropout.
- Keeps the M0 `soc_estimate_drift` failure mode + ASIL-C contract.

### adas (`modules/adas/`, impl `adas_stub`), ASIL-B
- Read `Vehicle.Speed`, `CruiseControl.IsActive`; read ODD from contract/params
  (`speedMaxKph`, `weather`). Engage LKA only inside ODD (speed ≤ speedMaxKph and
  active). Publish `LaneKeepingAssist.IsEngaged`. Exercises ODD + timing +
  failure-mode contract fields. **Not** an AI component (it is a stub — `ai.isAiComponent:false`).

### hmi (`modules/hmi/`), QM (above the safety line)
- Read `StateOfCharge.Current`. Publish `Cabin.HMI.IsLowBatteryWarningActive`
  (SoC < threshold). QM → freely swappable (useful for the M4 above-line
  swap-without-gate demo).

### body (`modules/body/`), QM
- Read `Vehicle.Speed` (track previous to detect deceleration). Publish
  `Body.Lights.Brake.IsActive` when decelerating. QM.

---

## Files to change / add
- `loom/sim/stimulus.py` (new) + wire into `InProcessOrchestrator` prelude.
- `plant/longitudinal/plant.py` (real dynamics).
- `modules/{powertrain,adas,hmi,body}/` (new: `service.py`, `contract.yaml`).
- `modules/bms/service.py` + `contract.yaml` (evolve to power-based discharge,
  add `ElectricMotor.Power` + `GrossCapacity` to `requires`).
- `scenarios/urban_drive.yaml` already carries the profile (M1 consumes it).
- tests: speed-tracking loop, per-module contracts, full-example M1 acceptance.

## Known simplifications (honest scoping)
- Single-pass fixed module order ⇒ one-tick signal lag; no dependency scheduler.
- Forward-Euler integration (RK4/Pacejka is M6 Motoquant).
- `num_steps = round(duration/dt)` drops the final endpoint when duration isn't a
  multiple of the step; `urban_drive` (20 s / 100 ms) divides evenly.
- 20 s of city driving consumes only a fraction of a percent of a 40 kWh pack —
  the SoC drop is small but real (physics is sane), and `changed_signals`
  detects it.
