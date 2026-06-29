"""HMI reference module (above the safety line, QM).

Reads battery State-of-Charge and drives a notional cabin display state — here, a
low-battery warning flag. QM means it is freely swappable above the safety line
(no re-validation gate), which makes it the natural subject for the M4 above-line
swap-without-gate demo.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loom.module import Module

if TYPE_CHECKING:
    from loom.bus.base import Bus

SOC_PATH = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"
LOW_BATTERY_WARNING_PATH = "Vehicle.Cabin.HMI.IsLowBatteryWarningActive"


class HmiDefault(Module):
    subsystem = "hmi"
    impl = "default"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self.low_battery_threshold_pct = float(self.params.get("lowBatteryThresholdPct", 20.0))

    def start(self, bus: Bus) -> None:
        bus.publish(LOW_BATTERY_WARNING_PATH, False, producer=self.module_id)

    def step(self, t: float, dt: float, bus: Bus) -> None:
        # Default to 100.0 only when the SoC path is genuinely unset — NOT via `or`,
        # which would treat a real, fully-depleted 0.0 as 100.0 and suppress the
        # warning at the most critical moment.
        raw = bus.read(SOC_PATH)
        soc = float(raw) if raw is not None else 100.0
        warn = soc < self.low_battery_threshold_pct
        bus.publish(LOW_BATTERY_WARNING_PATH, bool(warn), producer=self.module_id)


class HmiCustom(HmiDefault):
    """A custom (above-the-line, QM) HMI swap-in — same interface, an earlier
    low-battery warning threshold. Because HMI is QM, swapping it in is free (no
    re-validation gate): the M4 above-line swap-without-gate demo."""

    subsystem = "hmi"
    impl = "custom"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self.low_battery_threshold_pct = float(self.params.get("lowBatteryThresholdPct", 30.0))


IMPLEMENTATIONS = {"default": HmiDefault, "custom": HmiCustom}
