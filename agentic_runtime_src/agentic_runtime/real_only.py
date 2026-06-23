from __future__ import annotations

from typing import Any


UNSUPPORTED_RUNTIME_FIELD = "TASK_INPUT_FIELD_UNSUPPORTED"
SIMULATED_TASK_FIELDS = {"mock", "simulated", "simulation"}


def unsupported_task_field(data: dict[str, Any]) -> dict[str, Any] | None:
    fields = sorted(SIMULATED_TASK_FIELDS & set(data))
    if not fields:
        return None
    return {
        "success": False,
        "error_code": UNSUPPORTED_RUNTIME_FIELD,
        "reason": f"task input field is not supported in real-only runtime: {', '.join(fields)}",
        "fields": fields,
    }
