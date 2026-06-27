"""Safety-line swap gate (M4) — below-line (ASIL-*) implementation swaps require
explicit re-validation; above-line (QM) swaps are free."""
from __future__ import annotations

from loom.safety.gate import (
    GateDecision,
    Swap,
    current_config,
    detect_swaps,
    gate,
    load_lock,
    write_lock,
)

__all__ = [
    "GateDecision",
    "Swap",
    "current_config",
    "detect_swaps",
    "gate",
    "load_lock",
    "write_lock",
]
