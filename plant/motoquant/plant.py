"""Higher-fidelity plant behind the FMI boundary (HANDOFF §8 M6 — the Motoquant
plug-in point).

This is a **reference higher-fidelity plant** that drops into the same `Plant`
interface as the v0 `longitudinal` model, demonstrating the FMI-style plug-in
point: switching `plant.impl: longitudinal -> motoquant` runs the *same* scenario
through a richer engine with **no other code change**. The operator's external
Motoquant physics core would replace this class the same way (or be loaded as an
FMU via FMPy).

What's richer here vs `longitudinal`:
- **RK4** integration of the longitudinal dynamics (vs forward-Euler), so speed
  tracking is more accurate over the step.
- A **thermal battery model**: pack temperature rises with electrical load
  (resistive loss) and cools toward ambient — so `Temperature.Average` *varies*
  over the cycle instead of being constant.
- Resistive loss is folded into the electrical power and the ground-truth SoC.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loom.plant.base import Plant

if TYPE_CHECKING:
    from loom.bus.base import Bus

SPEED_PATH = "Vehicle.Speed"
TORQUE_PATH = "Vehicle.Powertrain.ElectricMotor.Torque"
POWER_PATH = "Vehicle.Powertrain.ElectricMotor.Power"
GROSS_CAPACITY_PATH = "Vehicle.Powertrain.TractionBattery.GrossCapacity"
BATTERY_TEMP_PATH = "Vehicle.Powertrain.TractionBattery.Temperature.Average"

GRAVITY = 9.81


class MotoquantPlant(Plant):
    impl = "motoquant"
    # Same signal manifest as the longitudinal plant -> interchangeable behind the boundary.
    provides = [
        {"path": SPEED_PATH, "unit": "km/h"},
        {"path": POWER_PATH, "unit": "W"},
        {"path": GROSS_CAPACITY_PATH, "unit": "kWh"},
        {"path": BATTERY_TEMP_PATH, "unit": "celsius"},
    ]
    requires = [
        {"path": TORQUE_PATH, "unit": "Nm", "optional": True},
    ]

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self.mass_kg = float(self.params.get("massKg", 1500.0))
        self.wheel_radius_m = float(self.params.get("wheelRadiusM", 0.31))
        self.battery_kwh = float(self.params.get("batteryKwh", 40.0))
        self.gear_ratio = float(self.params.get("gearRatio", 9.0))
        self.cda = float(self.params.get("dragCdA", 0.66))
        self.air_density = float(self.params.get("airDensity", 1.2))
        self.crr = float(self.params.get("rollingResistance", 0.01))
        self.efficiency = float(self.params.get("drivetrainEfficiency", 0.9))
        self.aux_load_w = float(self.params.get("auxLoadW", 300.0))
        # Thermal battery model parameters.
        self.ambient_temp_c = float(self.params.get("ambientTempC", 25.0))
        self.loss_fraction = float(self.params.get("resistiveLossFraction", 0.08))
        self.thermal_mass_j_per_c = float(self.params.get("thermalMassJperC", 60000.0))
        self.cooling_w_per_c = float(self.params.get("coolingWperC", 250.0))

        self.speed_mps = 0.0
        self.battery_temp_c = self.ambient_temp_c
        self.truth_soc = float(self.params.get("initialSocPercent", 80.0))

    def start(self, bus: Bus) -> None:
        bus.publish(SPEED_PATH, 0.0, unit="km/h", producer="plant.motoquant")
        bus.publish(POWER_PATH, 0.0, unit="W", producer="plant.motoquant")
        bus.publish(GROSS_CAPACITY_PATH, self.battery_kwh, unit="kWh", producer="plant.motoquant")
        bus.publish(BATTERY_TEMP_PATH, round(self.battery_temp_c, 4), unit="celsius", producer="plant.motoquant")

    def _accel(self, v: float, f_traction: float) -> float:
        moving = v > 1e-6
        f_drag = 0.5 * self.air_density * self.cda * v * v
        f_roll = self.crr * self.mass_kg * GRAVITY if moving else 0.0
        f_resist = f_drag + f_roll if moving else 0.0
        return (f_traction - f_resist) / self.mass_kg

    def step(self, t: float, dt: float, bus: Bus) -> None:
        torque_nm = float(bus.read(TORQUE_PATH, 0.0) or 0.0)
        f_traction = torque_nm * self.gear_ratio / self.wheel_radius_m
        v = self.speed_mps

        # RK4 integration of longitudinal speed (traction constant over the step).
        k1 = self._accel(v, f_traction)
        k2 = self._accel(v + 0.5 * dt * k1, f_traction)
        k3 = self._accel(v + 0.5 * dt * k2, f_traction)
        k4 = self._accel(v + dt * k3, f_traction)
        v_new = max(0.0, v + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4))
        self.speed_mps = v_new

        v_avg = 0.5 * (v + v_new)
        p_mech = f_traction * v_avg
        if p_mech >= 0.0:
            p_elec = p_mech / self.efficiency
        else:
            p_elec = p_mech * self.efficiency

        # Thermal battery model: resistive loss heats the pack; it cools to ambient.
        # Explicit-Euler update — stable while coolingWperC*dt << thermalMass (with
        # the defaults: 250*0.1/60000 ≈ 4e-4, comfortably stable).
        heat_w = abs(p_elec) * self.loss_fraction
        cooling_w = self.cooling_w_per_c * (self.battery_temp_c - self.ambient_temp_c)
        self.battery_temp_c += (heat_w - cooling_w) * dt / self.thermal_mass_j_per_c

        # Energy convention: p_elec is the battery *terminal* output (already /eff)
        # and heat_w is the additional internal pack loss, so ground-truth cell drain
        # = terminal + internal loss + aux. This is a deliberate (small) higher-fidelity
        # gap vs the BMS estimate (which only sees terminal Power) — well under the
        # soc_estimate_drift threshold; the intended drift demonstrator is bms.custom_x.
        draw_w = p_elec + heat_w + self.aux_load_w
        self.truth_soc = max(0.0, min(100.0, self.truth_soc - (draw_w * dt) / (self.battery_kwh * 3.6e6) * 100.0))

        bus.publish(SPEED_PATH, round(v_new * 3.6, 4), unit="km/h", producer="plant.motoquant")
        bus.publish(POWER_PATH, round(p_elec, 2), unit="W", producer="plant.motoquant")
        bus.publish(BATTERY_TEMP_PATH, round(self.battery_temp_c, 4), unit="celsius", producer="plant.motoquant")

    def truth(self) -> dict:
        return {"soc": round(self.truth_soc, 6)}


PLANT = MotoquantPlant
