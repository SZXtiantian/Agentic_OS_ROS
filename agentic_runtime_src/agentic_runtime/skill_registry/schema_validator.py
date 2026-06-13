from __future__ import annotations

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from agentic_runtime.errors import SchemaInvalidError


def validate_input(schema: dict, payload: dict) -> None:
    try:
        Draft7Validator(schema).validate(payload)
    except ValidationError as exc:
        raise SchemaInvalidError(exc.message) from exc
