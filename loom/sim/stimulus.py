"""Scenario stimulus — the 'driver + environment' that turns a scenario into
per-tick bus signals.

For M1 it interpolates the drive-cycle ``profile`` into a cruise set-speed and
publishes the environment signals modules consume. Fault injection (M3) will hook
the same per-tick prelude. These are non-module signal producers (producer label
``scenario``), valid sources for the M2 static checker alongside the plant.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loom.bus.base import Bus
    from loom.sim.scenario import Scenario

SPEED_SET_PATH = "Vehicle.ADAS.CruiseControl.SpeedSet"
CRUISE_ACTIVE_PATH = "Vehicle.ADAS.CruiseControl.IsActive"
CHARGING_PATH = "Vehicle.Powertrain.TractionBattery.Charging.IsCharging"
PRODUCER = "scenario"


def interpolate_profile(profile: list[dict], t: float, key: str = "targetSpeedKph") -> float:
    """Piecewise-linear interpolation of a profile column at time ``t``."""
    if not profile:
        return 0.0
    points = sorted(
        ((float(p["t"]), float(p.get(key, 0.0))) for p in profile), key=lambda x: x[0]
    )
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:], strict=False):
        if t0 <= t <= t1:
            if t1 == t0:
                return v1
            return v0 + (t - t0) / (t1 - t0) * (v1 - v0)
    return points[-1][1]


class ScenarioStimulus:
    # Signal manifest for the static checker — the scenario/driver is a valid
    # (non-module) producer of these environment signals.
    provides = [
        {"path": SPEED_SET_PATH, "unit": "km/h"},
        {"path": CRUISE_ACTIVE_PATH, "unit": None},
        {"path": CHARGING_PATH, "unit": None},
    ]

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    def apply(self, t: float, bus: Bus) -> None:
        target_kph = interpolate_profile(self.scenario.profile, t)
        bus.publish(SPEED_SET_PATH, round(target_kph, 4), unit="km/h", producer=PRODUCER)
        bus.publish(CRUISE_ACTIVE_PATH, True, producer=PRODUCER)
        bus.publish(CHARGING_PATH, False, producer=PRODUCER)
