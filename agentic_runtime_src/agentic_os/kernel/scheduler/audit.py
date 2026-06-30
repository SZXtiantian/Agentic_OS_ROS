from __future__ import annotations

from typing import Any

from agentic_os.kernel.hooks import sanitize_event_payload

from .models import utc_timestamp


_AUDIT_FIELD_DEFAULTS = {
    "agent_id": "",
    "app_id": "",
    "session_id": "",
    "task_graph_id": "",
    "node_id": "",
    "syscall_id": "",
    "resource_lease_id": "",
    "goal_id": "",
    "success": True,
    "error_code": "",
}
_AUDIT_ENVELOPE_KEYS = set(_AUDIT_FIELD_DEFAULTS)
_AUDIT_INTERNAL_KEYS = _AUDIT_ENVELOPE_KEYS | {"sanitized_metadata"}


class SchedulerAudit:
    def __init__(self, *, event_sink=None, audit_logger=None) -> None:
        self.event_sink = event_sink
        self.audit_logger = audit_logger
        self._recent_ids: list[str] = []

    def emit(self, event_type: str, **metadata: Any) -> str:
        payload = {**_AUDIT_FIELD_DEFAULTS, **metadata}
        sanitized = sanitize_event_payload(payload)
        sanitized["sanitized_metadata"] = {
            key: value
            for key, value in sanitized.items()
            if key not in _AUDIT_INTERNAL_KEYS
        }
        event_id = ""
        if self.event_sink is not None:
            event = self.event_sink.emit(event_type, **sanitized)
            event_id = str(event.event_id)
        audit_id = ""
        if self.audit_logger is not None:
            audit_id = self.audit_logger.write(
                {
                    "timestamp": utc_timestamp(),
                    "app_id": str(sanitized.get("app_id") or ""),
                    "session_id": str(sanitized.get("session_id") or ""),
                    "skill_name": event_type,
                    "args": sanitized,
                    "permission_result": "scheduler_checked",
                    "safety_result": str(sanitized.get("safety_result") or "scheduler_checked"),
                    "resource_lock_result": str(sanitized.get("resource_lock_result") or "scheduler_checked"),
                    "backend": "agentic_os.scheduler",
                    "status": "succeeded" if sanitized.get("success", True) else "failed",
                    "error_code": str(sanitized.get("error_code") or ""),
                    "duration_ms": int(sanitized.get("duration_ms") or 0),
                }
            )
        result_id = audit_id or event_id
        if result_id:
            self._recent_ids.append(result_id)
            self._recent_ids = self._recent_ids[-100:]
        return result_id

    def recent_ids(self, limit: int = 25) -> list[str]:
        return list(self._recent_ids[-limit:])
