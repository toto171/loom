"""Canonical filesystem locations for a Loom workspace.

The repo root is resolved from this package's own location (robust to the
current working directory) and can be overridden with the ``LOOM_ROOT`` env var.
"""
from __future__ import annotations

import os
from functools import cache
from pathlib import Path


@cache
def repo_root() -> Path:
    env = os.environ.get("LOOM_ROOT")
    if env:
        return Path(env).resolve()
    # loom/paths.py -> loom/ -> <repo root>
    return Path(__file__).resolve().parents[1]


def schema_dir() -> Path:
    return repo_root() / "spec" / "schema"


def modules_dir() -> Path:
    return repo_root() / "modules"


def scenarios_dir() -> Path:
    return repo_root() / "scenarios"


def plant_dir() -> Path:
    return repo_root() / "plant"


def runs_dir() -> Path:
    return repo_root() / "runs"


def locks_dir() -> Path:
    """Where per-vehicle validated-configuration locks live (safety-line gate).

    Committed, versioned state — the validated safety baseline travels with the
    repo as an input, NOT gitignored runtime state. (If it lived under runs/, a
    routine `rm -rf runs/` or a fresh clone would silently reset the baseline and
    let a below-line swap run ungated.)
    """
    return repo_root() / "locks"
