"""Body reference module (above the safety line, QM).

Drives notional body actuators from vehicle state — here, the brake lights, lit
when the vehicle is decelerating beyond a threshold. QM (freely swappable).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loom.module import Module

if TYPE_CHECKING:
    from loom.bus.base import Bus

SPEED_PATH = "Vehicle.Speed"
BRAKE_LIGHT_PATH = "Vehicle.Body.Lights.Brake.IsActive"


class BodyDefault(Module):
    subsystem = "body"
    impl = "default"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        # Light the brake lamps when decelerating faster than this (km/h per second).
        self.decel_threshold_kph_s = float(self.params.get("brakeDecelThresholdKphPerS", 3.0))
        self.prev_speed_kph = 0.0

    def start(self, bus: "Bus") -> None:
        bus.publish(BRAKE_LIGHT_PATH, False, producer=self.module_id)

    def step(self, t: float, dt: float, bus: "Bus") -> None:
        speed_kph = float(bus.read(SPEED_PATH, 0.0) or 0.0)
        decel_kph_s = (self.prev_speed_kph - speed_kph) / dt if dt > 0 else 0.0
        bus.publish(BRAKE_LIGHT_PATH, bool(decel_kph_s > self.decel_threshold_kph_s), producer=self.module_id)
        self.prev_speed_kph = speed_kph


IMPLEMENTATIONS = {"default": BodyDefault}
