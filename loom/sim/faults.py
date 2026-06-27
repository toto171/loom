"""Fault injection (HANDOFF §8 M3).

Applies a scenario's faults to the bus each tick. ``apply`` runs after the plant
publishes and before the modules step, so a corrupted sensor is what the consuming
modules and the monitors see this tick:

    stimulus -> plant.step -> faults.apply -> modules.step -> monitors -> record

Kinds:
- dropout: within [fromS, toS], force the target signal to None (sensor offline).
- stuck:   hold the value captured when the window opened (frozen sensor).
- latency: publish the value from ``delayTicks`` ticks ago (delayed sensor).
- crash:   the named module's outputs freeze — modelled by skipping that module's
           step (see ``crashed_modules``), so its last-published values persist.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loom.bus.base import Bus
    from loom.sim.scenario import Fault


_EPS = 1e-9  # tolerance for float tick accumulation at window boundaries


def _active(fault: Fault, t: float) -> bool:
    return fault.from_s - _EPS <= t <= fault.to_s + _EPS


class FaultInjector:
    def __init__(self, faults: list[Fault]) -> None:
        self.faults = list(faults)
        self._stuck_value: dict[str, object] = {}
        self._delay_buffer: dict[str, list] = {}

    def apply(self, t: float, bus: Bus) -> None:
        for fault in self.faults:
            if fault.kind == "crash" or not fault.target:
                continue
            if fault.kind == "latency":
                # Maintain the delay buffer every tick so the window has history.
                # Assumes the producer republishes the target fresh each tick before
                # faults.apply (true for plant sensors); the buffer is bounded.
                delay = int(fault.raw.get("delayTicks", 1))
                buf = self._delay_buffer.setdefault(fault.target, [])
                buf.append(bus.read(fault.target))
                if len(buf) > delay + 2:
                    del buf[0]
                if _active(fault, t) and len(buf) > delay:
                    bus.publish(fault.target, buf[-1 - delay], producer="fault.latency")
                continue
            if not _active(fault, t):
                self._stuck_value.pop(fault.target, None)  # reset once the window closes
                continue
            if fault.kind == "dropout":
                bus.publish(fault.target, None, producer="fault.dropout")
            elif fault.kind == "stuck":
                if fault.target not in self._stuck_value:
                    self._stuck_value[fault.target] = bus.read(fault.target)
                bus.publish(fault.target, self._stuck_value[fault.target], producer="fault.stuck")

    def crashed_modules(self, t: float) -> set[str]:
        """Module ids whose `crash` fault window is active at time t."""
        crashed: set[str] = set()
        for fault in self.faults:
            if fault.kind == "crash" and _active(fault, t):
                module = fault.raw.get("module")
                if module:
                    crashed.add(module)
        return crashed
