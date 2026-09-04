"""Draft 2020-12 JSON Schema validation for su-fenjingskill 3.1.6.

The schemas are the sole structural contract. Hand-written validators are limited
to cross-object and semantic rules.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Imported by formal validators for Draft 2020-12 Schema checks."

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


@lru_cache(maxsize=None)
def _validator(schema_name: str) -> Draft202012Validator:
    path = SCHEMA_DIR / schema_name
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _json_path(parts: list[Any], prefix: str = "") -> str:
    path = prefix.rstrip(".")
    if not path:
        path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif path == "$":
            path += f".{part}"
        else:
            path += f".{part}"
    return path


def validate_schema(
    value: Any,
    schema_name: str,
    *,
    code: str,
    prefix: str = "",
) -> list[dict[str, str]]:
    """Return deterministic issues for every schema violation."""
    issues: list[dict[str, str]] = []
    validator = _validator(schema_name)
    errors = sorted(
        validator.iter_errors(value),
        key=lambda item: (list(item.absolute_path), item.message),
    )
    for error in errors:
        issues.append(
            {
                "code": code,
                "path": _json_path(list(error.absolute_path), prefix),
                "message": error.message,
            }
        )
    return issues


def validate_formal_schema(value: Any) -> list[dict[str, str]]:
    return validate_schema(
        value,
        "director-shot-data.schema.json",
        code="FORMAL_SCHEMA_INVALID",
        prefix="shot_data",
    )


def validate_workspace_schema(value: Any) -> list[dict[str, str]]:
    return validate_schema(
        value,
        "director-workspace.schema.json",
        code="WORKSPACE_SCHEMA_INVALID",
        prefix="workspace",
    )
