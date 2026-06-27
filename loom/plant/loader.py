"""Resolve a plant impl name to a Plant instance.

Plant implementations live at ``plant/<impl>/plant.py`` and expose a ``PLANT``
attribute (the Plant subclass). Native-Python plants and FMU-backed plants
(loaded via FMPy) both satisfy the same interface.
"""
from __future__ import annotations

import importlib.util
import sys
from typing import Any

from loom.errors import LoomError
from loom.plant.base import Plant
from loom.paths import plant_dir


def load_plant(impl: str, params: dict[str, Any] | None = None) -> Plant:
    pdir = plant_dir() / impl
    plant_py = pdir / "plant.py"
    if not plant_py.exists():
        raise LoomError(f"plant impl '{impl}': no plant.py at {plant_py}")
    mod_name = f"loom_plant.{impl}.plant"
    spec = importlib.util.spec_from_file_location(mod_name, plant_py)
    if spec is None or spec.loader is None:
        raise LoomError(f"plant impl '{impl}': cannot import {plant_py}")
    py = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = py
    spec.loader.exec_module(py)
    plant_cls = getattr(py, "PLANT", None)
    if plant_cls is None:
        raise LoomError(f"plant impl '{impl}': plant.py defines no PLANT class")
    instance = plant_cls(params or {})
    if not isinstance(instance, Plant):
        raise LoomError(f"plant impl '{impl}' is not a loom Plant")
    return instance
