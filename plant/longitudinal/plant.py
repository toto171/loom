"""v0 longitudinal plant model (M1: real forward-Euler dynamics).

Reads the powertrain's commanded motor torque, integrates 1-D longitudinal
vehicle dynamics (traction vs aerodynamic drag + rolling resistance), and
publishes ground-truth ``Vehicle.Speed`` and electrical ``ElectricMotor.Power``.

Breadth over fidelity: forward-Euler, single gear ratio, no slip/tire model. A
high-fidelity Motoquant engine (RK4/Pacejka) — or any FMU loaded via FMPy —
replaces this class behind the same Plant interface at M6.
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

GRAVITY = 9.81  # m/s^2


class LongitudinalPlant(Plant):
    impl = "longitudinal"
    provides = [
        {"path": SPEED_PATH, "unit": "km/h"},
        {"path": POWER_PATH, "unit": "W"},
        {"path": GROSS_CAPACITY_PATH, "unit": "kWh"},
        {"path": BATTERY_TEMP_PATH, "unit": "celsius"},
    ]
    requires = [
        # Optional: with no powertrain the plant reads 0 torque (stationary vehicle),
        # so an absent producer is a warning, not a composition error.
        {"path": TORQUE_PATH, "unit": "Nm", "optional": True},
    ]

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self.mass_kg = float(self.params.get("massKg", 1500.0))
        self.wheel_radius_m = float(self.params.get("wheelRadiusM", 0.31))
        # Pack capacity is a vehicle-level param owned by the plant and published
        # to the bus as ground truth (the BMS reads it — single source of truth).
        self.battery_kwh = float(self.params.get("batteryKwh", 40.0))
        self.gear_ratio = float(self.params.get("gearRatio", 9.0))
        self.cda = float(self.params.get("dragCdA", 0.66))  # Cd * frontal area (m^2)
        self.air_density = float(self.params.get("airDensity", 1.2))  # kg/m^3
        self.crr = float(self.params.get("rollingResistance", 0.01))
        self.efficiency = float(self.params.get("drivetrainEfficiency", 0.9))
        self.battery_temp_c = float(self.params.get("batteryTempC", 25.0))  # constant for now; thermal model is M6
        self.speed_mps = 0.0  # ground-truth longitudinal speed
        # Ground-truth SoC the BMS estimate is compared against (truth: bindings).
        self.truth_soc = float(self.params.get("initialSocPercent", 80.0))
        self.aux_load_w = float(self.params.get("auxLoadW", 300.0))

    def start(self, bus: "Bus") -> None:
        bus.publish(SPEED_PATH, 0.0, unit="km/h", producer="plant.longitudinal")
        bus.publish(POWER_PATH, 0.0, unit="W", producer="plant.longitudinal")
        # Static ground-truth pack capacity, consumed by the BMS for SoC integration.
        bus.publish(
            GROSS_CAPACITY_PATH, self.battery_kwh, unit="kWh", producer="plant.longitudinal"
        )
        # Battery thermal ground truth (the sensor the BMS reads).
        bus.publish(
            BATTERY_TEMP_PATH, self.battery_temp_c, unit="celsius", producer="plant.longitudinal"
        )

    def step(self, t: float, dt: float, bus: "Bus") -> None:
        torque_nm = float(bus.read(TORQUE_PATH, 0.0) or 0.0)
        v = self.speed_mps

        f_traction = torque_nm * self.gear_ratio / self.wheel_radius_m
        moving = v > 1e-6
        f_drag = 0.5 * self.air_density * self.cda * v * v
        f_roll = self.crr * self.mass_kg * GRAVITY if moving else 0.0
        f_resist = f_drag + f_roll if moving else 0.0

        accel = (f_traction - f_resist) / self.mass_kg
        v_new = max(0.0, v + accel * dt)  # cannot roll backwards in this 1-D model
        self.speed_mps = v_new

        v_avg = 0.5 * (v + v_new)  # midpoint speed over the step (forward-Euler work)
        p_mech = f_traction * v_avg  # W at the wheels
        if p_mech >= 0.0:
            p_elec = p_mech / self.efficiency  # motoring: battery supplies more than wheels use
        else:
            p_elec = p_mech * self.efficiency  # regen: battery recovers less than wheels return

        bus.publish(SPEED_PATH, round(v_new * 3.6, 4), unit="km/h", producer="plant.longitudinal")
        bus.publish(POWER_PATH, round(p_elec, 2), unit="W", producer="plant.longitudinal")
        # Re-publish thermal ground truth each tick so a dropped temp sensor (M3) recovers.
        bus.publish(BATTERY_TEMP_PATH, self.battery_temp_c, unit="celsius", producer="plant.longitudinal")

        # Integrate ground-truth SoC (the same energy bookkeeping the BMS estimates).
        draw_w = p_elec + self.aux_load_w
        self.truth_soc = max(0.0, min(100.0, self.truth_soc - (draw_w * dt) / (self.battery_kwh * 3.6e6) * 100.0))

    def truth(self) -> dict:
        return {"soc": round(self.truth_soc, 6)}


PLANT = LongitudinalPlant
