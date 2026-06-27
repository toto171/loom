"""Module contract model, loader, and (later) static compatibility checker."""
from __future__ import annotations

from loom.contracts.model import Contract, FailureMode, Signal
from loom.contracts.loader import load_contract, parse_contract, validate_contract_data
from loom.contracts.checker import (
    CheckIssue,
    CheckReport,
    Participant,
    SignalEdge,
    check_composition,
    check_participants,
)
from loom.contracts.report import render_report

__all__ = [
    "Contract",
    "FailureMode",
    "Signal",
    "load_contract",
    "parse_contract",
    "validate_contract_data",
    "CheckIssue",
    "CheckReport",
    "Participant",
    "SignalEdge",
    "check_composition",
    "check_participants",
    "render_report",
]
