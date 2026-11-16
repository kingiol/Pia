from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    """Raised when an API payload does not satisfy its JSON Schema."""


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = ROOT / "contracts" / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_ROOT / f"{name}.json").read_text())


def validate_schema(payload: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if payload is None and "null" in expected_type:
            return
        allowed = [item for item in expected_type if item != "null"]
        if not any(_matches_type(payload, item) for item in allowed):
            raise SchemaValidationError(f"{path}: expected one of {allowed}")
    elif expected_type and not _matches_type(payload, expected_type):
        raise SchemaValidationError(f"{path}: expected {expected_type}")

    if "enum" in schema and payload not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value is not allowed")
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        if "minimum" in schema and payload < schema["minimum"]:
            raise SchemaValidationError(f"{path}: value is below minimum")

    if isinstance(payload, dict):
        for required in schema.get("required", []):
            if required not in payload:
                raise SchemaValidationError(f"{path}: missing required field '{required}'")
        properties = schema.get("properties", {})
        for key, value in payload.items():
            if key in properties:
                validate_schema(value, properties[key], f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(payload) - set(properties))
            if unknown:
                raise SchemaValidationError(f"{path}: unknown fields {unknown}")
    elif isinstance(payload, list) and schema.get("items"):
        for index, item in enumerate(payload):
            validate_schema(item, schema["items"], f"{path}[{index}]")
    elif isinstance(payload, str) and "minLength" in schema:
        if len(payload) < int(schema["minLength"]):
            raise SchemaValidationError(f"{path}: string is shorter than minLength")
    elif isinstance(payload, str) and schema.get("format") == "date":
        try:
            datetime.strptime(payload, "%Y-%m-%d")
        except ValueError as error:
            raise SchemaValidationError(f"{path}: expected YYYY-MM-DD") from error
    elif isinstance(payload, str) and schema.get("format") == "date-time":
        try:
            datetime.fromisoformat(payload.replace("Z", "+00:00"))
        except ValueError as error:
            raise SchemaValidationError(f"{path}: expected ISO date-time") from error


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def validate_named(payload: Any, name: str) -> None:
    validate_schema(payload, load_schema(name))
