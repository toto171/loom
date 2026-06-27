"""BMS (battery management system) reference module.

M1 behavior: integrate battery State-of-Charge from the actual electrical load —
the motor's electrical power (published by the plant) plus a small constant
auxiliary load — so SoC is coupled to how the vehicle is driven rather than a
fixed rate. Charging flips the sign. The ``soc_estimate_drift`` failure mode and
ASIL-C contract carry over from M0; the coulomb-counting fallback lands at M3.

The module is ticked in-process by the InProcessOrchestrator; the same class can
later run as a standalone container service against a networked KUKSA broker.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loom.module import Module

if TYPE_CHECKING:
    from loom.bus.base import Bus

SOC_PATH = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"
TEMP_PATH = "Vehicle.Powertrain.TractionBattery.Temperature.Average"
CHARGING_PATH = "Vehicle.Powertrain.TractionBattery.Charging.IsCharging"
MOTOR_POWER_PATH = "Vehicle.Powertrain.ElectricMotor.Power"
GROSS_CAPACITY_PATH = "Vehicle.Powertrain.TractionBattery.GrossCapacity"


class BmsDefault(Module):
    subsystem = "bms"
    impl = "default"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self.soc = float(self.params.get("initialSocPercent", 80.0))
        self.temp_c = float(self.params.get("ambientTempC", 25.0))  # last good reading from the sensor
        # Fallback pack capacity if the plant doesn't publish ground truth on the bus.
        self.fallback_capacity_kwh = float(self.params.get("batteryKwh", 40.0))
        self.aux_load_w = float(self.params.get("auxLoadW", 300.0))  # electronics/HVAC baseline
        self.charge_power_w = float(self.params.get("chargePowerW", 7000.0))

    def _publish(self, bus: Bus) -> None:
        bus.publish(SOC_PATH, round(self.soc, 4), unit="percent", producer=self.module_id)

    def start(self, bus: Bus) -> None:
        self._publish(bus)

    def step(self, t: float, dt: float, bus: Bus) -> None:
        # Read the battery thermal sensor (plant ground truth); hold last good value
        # if the sensor has dropped out (an M3 monitor flags the dropout separately).
        temp = bus.read(TEMP_PATH)
        if temp is not None:
            self.temp_c = float(temp)

        charging = bool(bus.read(CHARGING_PATH, False))
        if charging:
            draw_w = -abs(self.charge_power_w)  # negative draw = energy into the pack
        else:
            motor_power_w = float(bus.read(MOTOR_POWER_PATH, 0.0) or 0.0)
            draw_w = motor_power_w + self.aux_load_w

        capacity_kwh = float(bus.read(GROSS_CAPACITY_PATH, self.fallback_capacity_kwh) or self.fallback_capacity_kwh)
        capacity_j = capacity_kwh * 3.6e6
        delta_soc = (draw_w * dt) / capacity_j * 100.0
        self.soc = max(0.0, min(100.0, self.soc - delta_soc))
        self._publish(bus)


class BmsCustomX(BmsDefault):
    """A custom (third-party) BMS swap-in that estimates SoC with a systematic
    positive bias — i.e. it over-reports charge. Same ASIL-C contract and signal
    interface as the default, so it is interchangeable, but its bias trips the
    `soc_estimate_drift` runtime monitor (reported vs plant ground truth). This is
    the M4 below-line swap that demonstrates why re-validation matters.
    """

    subsystem = "bms"
    impl = "custom_x"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self.bias_pct = float(self.params.get("socBiasPct", 8.0))

    def _publish(self, bus: Bus) -> None:
        reported = max(0.0, min(100.0, self.soc + self.bias_pct))
        bus.publish(SOC_PATH, round(reported, 4), unit="percent", producer=self.module_id)


IMPLEMENTATIONS = {"default": BmsDefault, "custom_x": BmsCustomX}
