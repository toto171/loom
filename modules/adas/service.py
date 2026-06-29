"""ADAS stub reference module.

NOT a real driver (HANDOFF §11): it exercises the contract machinery — ODD
bounds, timing budget, declared failure modes — rather than perceiving or
planning. It engages a notional lane-keeping assist only inside its declared ODD
(speed within bounds and the driver/cruise system active). A real neural/VLA
driver would replace this as one module among many, with its ISO 8800 / SOTIF
fields populated (`ai.isAiComponent: true`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loom.module import Module

if TYPE_CHECKING:
    from loom.bus.base import Bus

SPEED_PATH = "Vehicle.Speed"
CRUISE_ACTIVE_PATH = "Vehicle.ADAS.CruiseControl.IsActive"
LKA_ENGAGED_PATH = "Vehicle.ADAS.LaneKeepingAssist.IsEngaged"
ODD_SPEED_MAX_PATH = "Vehicle.ADAS.LaneKeepingAssist.OddSpeedMaxKph"


class AdasStub(Module):
    subsystem = "adas"
    impl = "adas_stub"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        odd = self.params.get("odd", {}) or {}
        self.speed_max_kph = float(odd.get("speedMaxKph", 80.0))

    def start(self, bus: Bus) -> None:
        bus.publish(LKA_ENGAGED_PATH, False, producer=self.module_id)
        # Publish the EFFECTIVE ODD bound so the odd_exit monitor tracks the module's
        # configured value (the contract binds odd_speed_max_kph to this signal),
        # instead of a hard-coded constant that diverges when params override it.
        bus.publish(ODD_SPEED_MAX_PATH, self.speed_max_kph, unit="km/h", producer=self.module_id)

    def step(self, t: float, dt: float, bus: Bus) -> None:
        speed_kph = float(bus.read(SPEED_PATH, 0.0) or 0.0)
        cruise_active = bool(bus.read(CRUISE_ACTIVE_PATH, False))
        in_odd = 0.0 <= speed_kph <= self.speed_max_kph
        bus.publish(LKA_ENGAGED_PATH, bool(cruise_active and in_odd), producer=self.module_id)
        bus.publish(ODD_SPEED_MAX_PATH, self.speed_max_kph, unit="km/h", producer=self.module_id)


IMPLEMENTATIONS = {"adas_stub": AdasStub}
