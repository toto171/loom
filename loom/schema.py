"""Central JSON-Schema loading + validation for composition specs and contracts."""
from __future__ import annotations

import json
from enum import Enum
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator

from loom.paths import schema_dir


class SchemaName(str, Enum):
    COMPOSITION = "composition.schema.json"
    CONTRACT = "contract.schema.json"


@cache
def _validator(name: SchemaName) -> Draft202012Validator:
    schema = json.loads((schema_dir() / name.value).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_against(data: Any, name: SchemaName) -> list[str]:
    """Return a list of human-readable validation messages (empty == valid)."""
    validator = _validator(name)
    messages: list[str] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        messages.append(f"{loc}: {err.message}")
    return messages
