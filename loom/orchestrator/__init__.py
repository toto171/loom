"""Orchestrator abstraction + implementations.

The Orchestrator brings the selected modules + plant "up", drives a scenario,
records a trace, and tears down. Two implementations are planned from day one:

- InProcessOrchestrator  — ticks modules in one process over the in-process
  ShimBus (M0/M1). Deterministic, no container runtime required.
- ComposeOrchestrator    — docker compose + a networked KUKSA broker (later milestone).

Eclipse Ankaios can later replace Compose behind the same interface.
"""
from __future__ import annotations

from loom.orchestrator.base import Orchestrator, RunResult
from loom.orchestrator.compose import ComposeOrchestrator
from loom.orchestrator.inprocess import InProcessOrchestrator

__all__ = ["Orchestrator", "RunResult", "InProcessOrchestrator", "ComposeOrchestrator"]
