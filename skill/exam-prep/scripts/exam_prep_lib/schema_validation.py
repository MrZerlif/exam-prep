"""Small JSON-schema subset validator used without third-party dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SchemaError(ValueError):
    """Validation error containing the failing JSON path."""

    def __init__(self, path: str, message: str):
        self.path = path
        super().__init__(f"{path}: {message}")


SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
ENGINE_OWNED_PROPOSAL_FIELDS = {
    "recorded_at",
    "session_id",
    "timestamp",
    "expected_seconds",
    "elapsed_seconds",
    "assessment_integrity",
    "assessment_spec_hash",
    "canonical_assessment_hash",
    "derived_evidence_maturity",
    "independence",
    "exposure_classification",
    "verifier_result",
}


def _path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    return f"{parent}.{key}" if parent != "$" else f"$.{key}"


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_document(document: Any, schema: dict[str, Any], path: str = "$") -> None:
    if "anyOf" in schema:
        failures: list[str] = []
        for option in schema["anyOf"]:
            try:
                validate_document(document, option, path)
                break
            except SchemaError as exc:
                failures.append(str(exc))
        else:
            raise SchemaError(path, "document does not match any allowed schema variant")

    expected = schema.get("type")
    expected_types = expected if isinstance(expected, list) else [expected]
    if expected and not any(_matches_type(document, item) for item in expected_types):
        raise SchemaError(path, f"expected {expected}, got {type(document).__name__}")

    if "enum" in schema and document not in schema["enum"]:
        raise SchemaError(path, f"value {document!r} is not in enum")

    if isinstance(document, str):
        if "minLength" in schema and len(document) < schema["minLength"]:
            raise SchemaError(path, "string is shorter than minLength")

    if isinstance(document, (int, float)) and not isinstance(document, bool):
        if "minimum" in schema and document < schema["minimum"]:
            raise SchemaError(path, f"value is below minimum {schema['minimum']}")
        if "maximum" in schema and document > schema["maximum"]:
            raise SchemaError(path, f"value is above maximum {schema['maximum']}")

    if isinstance(document, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in document:
                raise SchemaError(_path(path, key), "required property is missing")

        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, value in document.items():
            child_path = _path(path, key)
            if key in properties:
                validate_document(value, properties[key], child_path)
            elif additional is False:
                raise SchemaError(child_path, "additional property is not allowed")
            elif isinstance(additional, dict):
                validate_document(value, additional, child_path)

    if isinstance(document, list) and isinstance(schema.get("items"), dict):
        for index, value in enumerate(document):
            validate_document(value, schema["items"], _path(path, index))


def load_schema(name: str) -> dict[str, Any]:
    with (SCHEMA_ROOT / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_observation_proposal(document: dict[str, Any]) -> None:
    if not isinstance(document, dict):
        raise SchemaError("$", "observation proposal must be an object")
    for field in ENGINE_OWNED_PROPOSAL_FIELDS:
        if field in document:
            raise SchemaError(_path("$", field), "engine-owned field is not accepted from LLM")
    schema_name = (
        "observation-proposal-v2.schema.json"
        if document.get("schema_version") == 2
        else "observation-proposal.schema.json"
    )
    validate_document(document, load_schema(schema_name))


def validate_observation_event(document: dict[str, Any]) -> None:
    "Validate a canonical event, dispatching explicitly between v1 and v2."

    if not isinstance(document, dict):
        raise SchemaError("$", "observation event must be an object")
    schema_name = (
        "observation-event-v2.schema.json"
        if document.get("schema_version") == 2
        else "observation-event.schema.json"
    )
    validate_document(document, load_schema(schema_name))


def validate_state_bundle(bundle: dict[str, Any]) -> None:
    schema_name = "targets.schema.json" if bundle.get("schema_version") == 2 else "concepts.schema.json"
    validate_document(bundle, load_schema(schema_name))

