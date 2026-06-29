"""Deployment manifest generation — turn a Loom composition into the descriptor a
workload orchestrator consumes. Today: Eclipse Ankaios (``loom/deploy/ankaios.py``),
the automotive workload orchestrator that can replace Docker-Compose behind the
:class:`loom.orchestrator.base.Orchestrator` interface.
"""
from __future__ import annotations

from loom.deploy.ankaios import build_ankaios_manifest, dump_ankaios_manifest

__all__ = ["build_ankaios_manifest", "dump_ankaios_manifest"]
