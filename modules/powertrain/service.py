"""Powertrain reference module — a P-controller that tracks the cruise set-speed.

Reads the commanded set-speed (from the scenario driver) and ground-truth speed
(from the plant), and commands motor torque proportional to the speed error
(negative torque = regenerative braking). The plant integrates that torque into
the next tick's speed, closing the cross-module control loop over VSS signals.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loom.module import Module

if TYPE_CHECKING:
    from loom.bus.base import Bus

SPEED_SET_PATH = "Vehicle.ADAS.CruiseControl.SpeedSet"
SPEED_PATH = "Vehicle.Speed"
TORQUE_PATH = "Vehicle.Powertrain.ElectricMotor.Torque"


class PowertrainDefault(Module):
    subsystem = "powertrain"
    impl = "default"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self.kp = float(self.params.get("speedKp", 200.0))  # Nm per (m/s) of error
        self.max_torque_nm = float(self.params.get("maxTorqueNm", 300.0))

    def start(self, bus: Bus) -> None:
        bus.publish(TORQUE_PATH, 0.0, unit="Nm", producer=self.module_id)

    def step(self, t: float, dt: float, bus: Bus) -> None:
        set_kph = float(bus.read(SPEED_SET_PATH, 0.0) or 0.0)
        speed_kph = float(bus.read(SPEED_PATH, 0.0) or 0.0)
        error_mps = (set_kph - speed_kph) / 3.6
        torque = max(-self.max_torque_nm, min(self.max_torque_nm, self.kp * error_mps))
        bus.publish(TORQUE_PATH, round(torque, 4), unit="Nm", producer=self.module_id)


class PowertrainCustomUnits(PowertrainDefault):
    """A powertrain swap that carries a genuine units defect.

    Its contract declares it reads ``Vehicle.Speed`` in **mph**, but the plant
    publishes that signal in **km/h**. The implementation is faithful to its
    (wrong) contract — it converts the read value as if it were mph — so the bug
    is real, not just a metadata typo. The static ``unit_consistency`` check
    catches the mismatch and refuses the composition before it can ever run,
    demonstrating the checker end-to-end (cf. ``spec/vehicle.broken_units.yaml``).
    """

    impl = "custom_units"

    def step(self, t: float, dt: float, bus: Bus) -> None:
        set_kph = float(bus.read(SPEED_SET_PATH, 0.0) or 0.0)
        speed_mph = float(bus.read(SPEED_PATH, 0.0) or 0.0)  # contract says mph (it isn't)
        error_mps = (set_kph / 3.6) - (speed_mph * 0.44704)
        torque = max(-self.max_torque_nm, min(self.max_torque_nm, self.kp * error_mps))
        bus.publish(TORQUE_PATH, round(torque, 4), unit="Nm", producer=self.module_id)


IMPLEMENTATIONS = {"default": PowertrainDefault, "custom_units": PowertrainCustomUnits}
