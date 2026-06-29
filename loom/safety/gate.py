"""The safety-line swap gate (HANDOFF §5.2 final rule, §8 M4).

A vehicle's last-validated configuration (which implementation each subsystem
used) is recorded in a **lock**. On a subsequent run, swapping a subsystem's
implementation is detected by diffing against the lock. A swap that touches the
**safety line** — i.e. either the old or new implementation is ASIL-* (below the
line) — is **refused** unless the operator passes ``--revalidate``, in which case
it proceeds and a re-validation entry is recorded. Above-line (QM) swaps are free.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from loom.errors import LoomError

_ABSENT = "(absent)"
_UNKNOWN_ASIL = "ASIL (unspecified)"  # fail-safe: a malformed lock entry gates rather than slips through


def _is_below_line(safety_level: str) -> bool:
    return str(safety_level).upper().startswith("ASIL")


@dataclass
class Swap:
    subsystem: str
    old_impl: str
    new_impl: str
    old_safety_level: str
    new_safety_level: str

    @property
    def below_line(self) -> bool:
        """A swap crosses the safety line if either side is ASIL-* — replacing an
        ASIL module, or introducing one where there was a QM module, both gate."""
        return _is_below_line(self.old_safety_level) or _is_below_line(self.new_safety_level)

    def describe(self) -> str:
        return (
            f"{self.subsystem}: {self.old_impl} [{self.old_safety_level}] -> "
            f"{self.new_impl} [{self.new_safety_level}]"
        )


@dataclass
class GateDecision:
    swaps: list[Swap]
    gated_swaps: list[Swap]  # the below-line swaps that need re-validation
    allowed: bool
    refused_reason: str | None = None


def current_config(modules) -> dict[str, dict]:
    """Map subsystem -> {impl, safetyLevel} for the resolved modules."""
    return {
        m.subsystem: {"impl": m.impl, "safetyLevel": m.contract.safety_level}
        for m in modules
    }


def detect_swaps(current: dict[str, dict], lock: dict | None) -> list[Swap]:
    """A swap is any subsystem-level difference between the locked (last-validated)
    config and the current one: an implementation change, an ADDED subsystem, or a
    REMOVED subsystem. Diffing over the *union* of keys means introducing or
    dropping a below-line subsystem is gated too — not just replacing one. A fresh
    vehicle (no lock) has no swaps (trust-on-first-use; see the CLI baseline notice)."""
    if not lock:
        return []
    locked = lock.get("subsystems", {})
    swaps: list[Swap] = []
    for subsystem in sorted(set(current) | set(locked)):
        cur = current.get(subsystem)
        prev = locked.get(subsystem)
        if cur and prev:
            if prev.get("impl") != cur["impl"]:
                # A missing locked safetyLevel fails SAFE (treated as below-line) so
                # a malformed lock gates rather than silently un-gating the swap.
                old_sl = prev.get("safetyLevel") or _UNKNOWN_ASIL
                swaps.append(Swap(subsystem, prev.get("impl", "?"), cur["impl"], old_sl, cur["safetyLevel"]))
        elif cur and not prev:  # subsystem added since the baseline
            swaps.append(Swap(subsystem, _ABSENT, cur["impl"], "", cur["safetyLevel"]))
        elif prev and not cur:  # subsystem removed since the baseline
            # A missing locked safetyLevel on a removal also fails SAFE (gated),
            # matching the changed-impl branch above.
            swaps.append(Swap(subsystem, prev.get("impl", "?"), _ABSENT, prev.get("safetyLevel") or _UNKNOWN_ASIL, ""))
    return swaps


def gate(swaps: list[Swap], revalidate: bool) -> GateDecision:
    gated = [s for s in swaps if s.below_line]
    if gated and not revalidate:
        reason = (
            "below-the-safety-line implementation swap(s) require --revalidate:\n  - "
            + "\n  - ".join(s.describe() for s in gated)
        )
        return GateDecision(swaps=swaps, gated_swaps=gated, allowed=False, refused_reason=reason)
    return GateDecision(swaps=swaps, gated_swaps=gated, allowed=True)


def load_lock(path: str | Path) -> dict | None:
    """Load the validated-baseline lock, failing SAFE on corruption.

    locks/ is committed, hand-editable, merge-conflict-prone state, so a corrupt
    or non-object lock raises a domain error (the run fails closed — a swap is
    never allowed through an untrusted baseline) rather than crashing with a raw
    traceback or being silently treated as absent."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        raise LoomError(
            f"safety lock {path} is corrupt/unparseable ({exc}); the validated baseline "
            "cannot be trusted — restore it or delete it to re-establish a baseline"
        ) from exc
    if not isinstance(data, dict):
        raise LoomError(
            f"safety lock {path} is not a JSON object (got {type(data).__name__}); "
            "the validated baseline cannot be trusted"
        )
    return data


def write_lock(path: str | Path, vehicle: str, current: dict[str, dict]) -> None:
    """Atomically persist the validated config (write a temp file + os.replace) so a
    concurrent reader never observes a partial or missing lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"vehicle": vehicle, "subsystems": current}, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)
