"""Scenario model, trace recorder, and (later) fault injection."""
from __future__ import annotations

from loom.sim.scenario import Fault, Scenario, load_scenario, parse_scenario
from loom.sim.stimulus import ScenarioStimulus, interpolate_profile
from loom.sim.trace import Trace

__all__ = [
    "Fault",
    "Scenario",
    "load_scenario",
    "parse_scenario",
    "ScenarioStimulus",
    "interpolate_profile",
    "Trace",
]
