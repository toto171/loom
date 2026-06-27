"""Enumerate the workspace — subsystems/implementations, plants, scenarios, specs,
and past runs — for the web dashboard (and any other front-end)."""
from __future__ import annotations

import json
from pathlib import Path

from loom.compose.resolve import list_impls, resolve_module
from loom.paths import modules_dir, plant_dir, runs_dir, scenarios_dir, repo_root


def list_subsystems() -> dict[str, list[dict]]:
    """subsystem -> list of {impl, module_id, safetyLevel, license, belowLine,
    provides, requires} for every shipped implementation."""
    out: dict[str, list[dict]] = {}
    if not modules_dir().is_dir():
        return out
    for sub_dir in sorted(p for p in modules_dir().iterdir() if p.is_dir()):
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


def list_runs() -> list[dict]:
    """Recent runs (newest first) — each run.json summary."""
    runs = runs_dir()
    if not runs.is_dir():
        return []
    out = []
    for d in sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True):
        rj = d / "run.json"
        if rj.exists():
            try:
                out.append(json.loads(rj.read_text(encoding="utf-8")))
            except Exception:
                continue
    return out


def load_run(run_id: str) -> dict | None:
    base = runs_dir().resolve()
    rj = (base / run_id / "run.json").resolve()
    if not rj.is_relative_to(base) or not rj.exists():  # guard against ../ traversal
        return None
    return json.loads(rj.read_text(encoding="utf-8"))


def run_artifact(run_id: str, name: str) -> Path | None:
    """Resolve an artifact path inside a run dir, guarding against path traversal."""
    base = (runs_dir() / run_id).resolve()
    target = (base / name).resolve()
    if base not in target.parents and target != base:
        return None
    return target if target.exists() else None
