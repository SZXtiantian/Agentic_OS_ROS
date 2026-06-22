from __future__ import annotations

from typing import Any

from .models import SessionRecord, SessionStatus, utc_now
from .store import SessionStore


class SessionManager:
    def __init__(self, store: SessionStore) -> None:
        self.store = store

    def create_session(self, app_id: str, task: dict[str, Any] | None = None) -> SessionRecord:
        return self.store.save(SessionRecord.create(app_id, task=task))

    def start_session(self, session_id: str) -> SessionRecord:
        record = self.store.require(session_id)
        record.status = SessionStatus.RUNNING
        record.started_at = record.started_at or utc_now()
        return self.store.save(record)

    def set_current_skill(self, session_id: str, skill_name: str) -> SessionRecord | None:
        record = self.store.get(session_id)
        if record is None:
            return None
        record.current_skill = skill_name
        return self.store.save(record)

    def complete_session(self, session_id: str, result: dict[str, Any]) -> SessionRecord:
        record = self.store.require(session_id)
        record.status = SessionStatus.COMPLETED
        record.current_skill = ""
        record.result = result
        record.error_code = ""
        record.ended_at = utc_now()
        return self.store.save(record)

    def fail_session(self, session_id: str, error_code: str, result: dict[str, Any] | None = None) -> SessionRecord:
        record = self.store.require(session_id)
        record.status = SessionStatus.FAILED
        record.current_skill = ""
        record.result = result or {"success": False, "error_code": error_code}
        record.error_code = error_code
        record.ended_at = utc_now()
        return self.store.save(record)

    def stop_session(self, session_id: str, reason: str = "operator_requested") -> SessionRecord:
        record = self.store.require(session_id)
        record.stop_requested = True
        if record.status not in SessionStatus.TERMINAL:
            record.status = SessionStatus.CANCELLED
            record.current_skill = ""
            record.error_code = "SESSION_STOPPED"
            record.result = {"success": False, "error_code": "SESSION_STOPPED", "reason": reason}
            record.ended_at = utc_now()
        return self.store.save(record)

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self.store.get(session_id)

    def list_sessions(self, limit: int | None = None) -> list[SessionRecord]:
        return self.store.list(limit=limit)

    def append_syscall(self, session_id: str, syscall: dict[str, Any]) -> None:
        self.store.append_syscall(session_id, syscall)

    def read_syscalls(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self.store.read_syscalls(session_id, limit=limit)
