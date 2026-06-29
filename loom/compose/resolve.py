"""Resolve a composition's subsystem selections to concrete Modules + contracts.

Each subsystem lives at ``modules/<subsystem>/`` with a ``service.py`` that
exposes an ``IMPLEMENTATIONS`` dict (impl name -> Module subclass). Contracts are
``contract.yaml`` for the ``default`` impl and ``contract.<impl>.yaml`` otherwise.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loom.compose.model import Composition
from loom.contracts.loader import load_contract
from loom.contracts.model import Contract
from loom.errors import ModuleResolutionError
from loom.module import Module
from loom.paths import modules_dir

_IMPL_REGISTRY_ATTR = "IMPLEMENTATIONS"

# Cache loaded service modules by (resolved path, mtime) so a subsystem's service.py
# is exec'd at most once and re-exec'd only when the file changes — list_subsystems()
# and resolve_modules() otherwise re-import the same source repeatedly per impl.
_SERVICE_CACHE: dict[str, tuple[int, Any]] = {}


@dataclass
class ResolvedModule:
    subsystem: str
    impl: str
    instance: Module
    contract: Contract

    @property
    def module_id(self) -> str:
        return f"{self.subsystem}.{self.impl}"


def _load_service(subsystem: str, mod_dir: Path):
    service_py = mod_dir / "service.py"
    if not service_py.exists():
        raise ModuleResolutionError(
            f"subsystem '{subsystem}': no service.py at {service_py}"
        )
    key = str(service_py.resolve())
    mtime = service_py.stat().st_mtime_ns
    cached = _SERVICE_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    mod_name = f"loom_modules.{subsystem}.service"
    spec = importlib.util.spec_from_file_location(mod_name, service_py)
    if spec is None or spec.loader is None:
        raise ModuleResolutionError(f"subsystem '{subsystem}': cannot import {service_py}")
    py = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = py
    spec.loader.exec_module(py)
    _SERVICE_CACHE[key] = (mtime, py)
    return py


def _contract_path(impl: str, mod_dir: Path) -> Path:
    # A subsystem's base contract.yaml may belong to a single non-default impl (e.g.
    # adas.adas_stub), so the fallback is legitimate — but resolve_module asserts the
    # loaded contract's `module` matches the resolved impl, so a non-default impl can
    # never silently inherit a DIFFERENT impl's contract (and its safety level).
    if impl == "default":
        default = mod_dir / "contract.yaml"
        if default.exists():
            return default
    specific = mod_dir / f"contract.{impl}.yaml"
    if specific.exists():
        return specific
    return mod_dir / "contract.yaml"


def resolve_module(
    subsystem: str, impl: str, params: dict[str, Any] | None = None
) -> ResolvedModule:
    mod_dir = modules_dir() / subsystem
    if not mod_dir.is_dir():
        raise ModuleResolutionError(
            f"subsystem '{subsystem}': no module directory at {mod_dir}"
        )
    service = _load_service(subsystem, mod_dir)
    registry = getattr(service, _IMPL_REGISTRY_ATTR, None)
    if not isinstance(registry, dict) or impl not in registry:
        available = sorted(registry) if isinstance(registry, dict) else []
        raise ModuleResolutionError(
            f"subsystem '{subsystem}': implementation '{impl}' not found "
            f"(available: {available})"
        )
    contract = load_contract(_contract_path(impl, mod_dir))
    # Defense in depth: the resolved contract must declare THIS module's identity, so
    # a mismatched/copy-pasted contract can't smuggle in a wrong safety level.
    expected = f"{subsystem}.{impl}"
    if contract.module != expected:
        raise ModuleResolutionError(
            f"subsystem '{subsystem}': implementation '{impl}' resolves to a contract "
            f"declaring module '{contract.module}' (expected '{expected}')"
        )
    instance = registry[impl](params or {})
    if not isinstance(instance, Module):
        raise ModuleResolutionError(f"{subsystem}.{impl} is not a loom Module")
    return ResolvedModule(
        subsystem=subsystem, impl=impl, instance=instance, contract=contract
    )


def resolve_modules(comp: Composition) -> list[ResolvedModule]:
    return [resolve_module(s.name, s.impl, s.params) for s in comp.subsystems]


def list_impls(subsystem: str) -> list[str]:
    """Available implementation names for a subsystem (its service IMPLEMENTATIONS)."""
    mod_dir = modules_dir() / subsystem
    if not mod_dir.is_dir():
        return []
    service = _load_service(subsystem, mod_dir)
    registry = getattr(service, _IMPL_REGISTRY_ATTR, None)
    return sorted(registry) if isinstance(registry, dict) else []
