from __future__ import annotations

from typing import Any

APP_RESULT_INVALID = "APP_RESULT_INVALID"


def validate_app_result_payload(value: Any, *, source: str = "app") -> tuple[dict[str, Any], bool]:
    if not isinstance(value, dict):
        return _invalid_payload(
            "app returned non-dict result",
            source=source,
            raw_type=type(value).__name__,
        ), False
    if "success" not in value:
        return _invalid_payload(
            "app result missing success field",
            source=source,
            keys=sorted(str(key) for key in value.keys()),
        ), False
    if not isinstance(value["success"], bool):
        return _invalid_payload(
            "app result success field must be bool",
            source=source,
            raw_type=type(value["success"]).__name__,
            keys=sorted(str(key) for key in value.keys()),
        ), False
    return value, True


def normalize_app_invocation_result(value: Any, *, source: str = "app") -> dict[str, Any]:
    if not isinstance(value, dict):
        payload, _ = validate_app_result_payload(value, source=source)
        return payload
    if "result" not in value:
        payload, valid = validate_app_result_payload(value, source=source)
        return payload if not valid else value

    payload, valid = validate_app_result_payload(value.get("result"), source=source)
    if valid:
        return value
    normalized = dict(value)
    normalized["success"] = False
    normalized["status"] = "failed"
    normalized["result"] = payload
    return normalized


def _invalid_payload(
    reason: str,
    *,
    source: str,
    raw_type: str = "",
    keys: list[str] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": source}
    if raw_type:
        metadata["raw_type"] = raw_type
    if keys is not None:
        metadata["keys"] = keys
    return {
        "success": False,
        "error_code": APP_RESULT_INVALID,
        "reason": reason,
        "metadata": metadata,
    }
