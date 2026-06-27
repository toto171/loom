"""Plant model abstraction (FMI-style boundary) + loader."""
from __future__ import annotations

from loom.plant.base import Plant
from loom.plant.loader import load_plant

__all__ = ["Plant", "load_plant"]
