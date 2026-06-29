"""Enumerate the workspace — subsystems/implementations, plants, scenarios, specs,
and past runs — for the web dashboard (and any other front-end)."""
from __future__ import annotations

import json
from pathlib import Path

from loom.compose.resolve import list_impls, resolve_module
from loom.paths import modules_dir, plant_dir, repo_root, runs_dir, scenarios_dir


def _normalize_summary(rec: dict) -> dict:
    """Backfill the top-level keys the dashboard templates read, so a partial or
    older run.json renders gracefully instead of raising on a missing key."""
    if not isinstance(rec, dict):
        return rec
    rec.setdefault("assurance", None)
    rec.setdefault("staticCheck", None)
    rec.setdefault("violations", [])
    rec.setdefault("swaps", [])
    rec.setdefault("modules", [])
    rec.setdefault("changedSignals", {})
    rec.setdefault("skippedMonitors", [])
    rec.setdefault("revalidation", None)
    return rec


_SUBSYSTEMS_CACHE: dict[str, tuple[int, dict]] = {}


def list_subsystems() -> dict[str, list[dict]]:
    """subsystem -> list of {impl, module_id, safetyLevel, license, belowLine,
    provides, requires} for every shipped implementation.

    Cached by a modules/ source-mtime signature: the dashboard's hot pages reuse the
    parsed result, but editing any service.py/contract*.yaml invalidates it (so no
    staleness). Callers must treat the result as read-only (the same object is reused)."""
    md = modules_dir()
    if not md.is_dir():
        return {}
    sig = max(
        (p.stat().st_mtime_ns for p in md.rglob("*") if p.suffix in (".py", ".yaml")),
        default=0,
    )
    cached = _SUBSYSTEMS_CACHE.get("v")
    if cached is not None and cached[0] == sig:
        return cached[1]
    out: dict[str, list[dict]] = {}
    for sub_dir in sorted(p for p in md.iterdir() if p.is_dir()):
        sub = sub_dir.name
        impls = []
        for impl in list_impls(sub):
            try:
                rm = resolve_module(sub, impl, {})
            except Exception:
                continue
            c = rm.contract
            impls.append({
                "impl": impl,
                "module_id": rm.module_id,
                "safetyLevel": c.safety_level,
                "license": c.license,
                "belowLine": c.is_below_safety_line,
                "provides": [s.path for s in c.provides],
                "requires": [s.path for s in c.requires],
            })
        if impls:
            out[sub] = impls
    _SUBSYSTEMS_CACHE["v"] = (sig, out)
    return out


def list_plants() -> list[str]:
    if not plant_dir().is_dir():
        return []
    return sorted(p.name for p in plant_dir().iterdir() if (p / "plant.py").exists())


def list_scenarios() -> list[str]:
    if not scenarios_dir().is_dir():
        return []
    return sorted(p.stem for p in scenarios_dir().glob("*.yaml"))


def list_specs() -> list[str]:
    spec_dir = repo_root() / "spec"
    if not spec_dir.is_dir():
        return []
    return sorted(p.name for p in spec_dir.glob("*.yaml"))


def list_runs(limit: int | None = None) -> list[dict]:
    """Recent runs (newest first) — each run.json summary. With ``limit`` set, stop
    after collecting that many (dirs are sorted newest-first), so a page that shows
    the latest N doesn't read and parse every run.json on disk."""
    runs = runs_dir()
    if not runs.is_dir():
        return []
    out = []
    for d in sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True):
        rj = d / "run.json"
        if rj.exists():
            try:
                out.append(_normalize_summary(json.loads(rj.read_text(encoding="utf-8"))))
            except Exception:
                continue
            if limit is not None and len(out) >= limit:
                break
    return out


def load_run(run_id: str) -> dict | None:
    base = runs_dir().resolve()
    rj = (base / run_id / "run.json").resolve()
    if not rj.is_relative_to(base) or not rj.exists():  # guard against ../ traversal
        return None
    try:
        return _normalize_summary(json.loads(rj.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):  # a corrupt run.json -> 404, not a 500
        return None


def run_artifact(run_id: str, name: str) -> Path | None:
    """Resolve an artifact path inside a run dir, guarding against path traversal."""
    # Containment base is the trusted runs/ dir — never derived from the untrusted
    # run_id (which can contain ../), so a crafted run_id cannot escape runs/.
    base = runs_dir().resolve()
    target = (base / run_id / name).resolve()
    if not target.is_relative_to(base):
        return None
    return target if target.exists() else None
