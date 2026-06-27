"""Composition spec parsing, validation, and module resolution."""
from __future__ import annotations

from loom.compose.model import Composition, SubsystemSelection
from loom.compose.loader import (
    load_composition,
    parse_composition,
    validate_composition_data,
)
from loom.compose.resolve import ResolvedModule, resolve_module, resolve_modules

__all__ = [
    "Composition",
    "SubsystemSelection",
    "load_composition",
    "parse_composition",
    "validate_composition_data",
    "ResolvedModule",
    "resolve_module",
    "resolve_modules",
]
