from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from agentic_runtime.provider_contracts import human_operator_contract
from agentic_runtime.types import new_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HumanQueuePaths:
    root: Path

    @property
    def requests(self) -> Path:
        return self.root / "requests.jsonl"

    @property
    def responses(self) -> Path:
        return self.root / "responses.jsonl"

    @property
    def events(self) -> Path:
        return self.root / "events.jsonl"


class FileHumanQueueChannel:
    """Durable operator queue for real human-in-the-loop requests.

    The runtime writes requests to JSONL and waits for an operator/system to
    append a matching response. It never manufactures an answer.
    """

    def __init__(self, root: str | Path, *, poll_interval_s: float = 0.05) -> None:
        self.paths = HumanQueuePaths(Path(root).expanduser().resolve())
        self.poll_interval_s = poll_interval_s
        self._lock = Lock()
        self._active: dict[str, asyncio.Event] = {}
        self._last_error = ""
        self.paths.root.mkdir(parents=True, exist_ok=True)

    async def ask(
        self,
        *,
        question: str,
        options: list[Any] | None = None,
        timeout_s: int | float = 60,
        require_confirmation: bool = False,
        app_id: str = "",
        session_id: str = "kernel",
        correlation_id: str = "",
        cancel_event: Any | None = None,
    ) -> dict[str, Any]:
        if not question:
            return {"success": False, "answered": False, "answer": "", "error_code": "HUMAN_QUESTION_REQUIRED"}
        correlation_id = correlation_id or new_id("human")
        timeout_s = max(0.0, float(timeout_s))
        deadline = time.monotonic() + timeout_s
        active_cancel = asyncio.Event()
        with self._lock:
            self._active[correlation_id] = active_cancel
        request = {
            "type": "human_request",
            "correlation_id": correlation_id,
            "app_id": app_id,
            "session_id": session_id,
            "question": question,
            "options": list(options or []),
            "timeout_s": timeout_s,
            "require_confirmation": bool(require_confirmation),
            "created_at": utc_now(),
            "status": "pending",
        }
        self._append_jsonl(self.paths.requests, request)
        try:
            while True:
                response = self._find_response(correlation_id)
                if response is not None:
                    answer = str(response.get("answer", ""))
                    self._append_jsonl(
                        self.paths.events,
                        {**request, "type": "human_answered", "answer": answer, "answered_at": utc_now()},
                    )
                    return {
                        "success": True,
                        "answered": True,
                        "answer": answer,
                        "reason": str(response.get("reason", "")),
                        "correlation_id": correlation_id,
                        "request_path": str(self.paths.requests),
                        "response_path": str(self.paths.responses),
                    }
                if active_cancel.is_set() or (cancel_event is not None and cancel_event.is_set()):
                    self._append_jsonl(
                        self.paths.events,
                        {**request, "type": "human_cancelled", "cancelled_at": utc_now()},
                    )
                    return {
                        "success": False,
                        "answered": False,
                        "answer": "",
                        "error_code": "HUMAN_CANCELLED",
                        "reason": "human request cancelled",
                        "correlation_id": correlation_id,
                    }
                if time.monotonic() >= deadline:
                    self._append_jsonl(self.paths.events, {**request, "type": "human_timeout", "timed_out_at": utc_now()})
                    return {
                        "success": False,
                        "answered": False,
                        "answer": "",
                        "error_code": "HUMAN_TIMEOUT",
                        "reason": "human response timed out",
                        "correlation_id": correlation_id,
                        "request_path": str(self.paths.requests),
                    }
                await asyncio.sleep(min(self.poll_interval_s, max(0.0, deadline - time.monotonic())))
        finally:
            with self._lock:
                self._active.pop(correlation_id, None)

    def cancel(self, correlation_id: str = "", *, session_id: str = "") -> dict[str, Any]:
        cancelled: list[str] = []
        with self._lock:
            for active_id, event in list(self._active.items()):
                if correlation_id and active_id != correlation_id:
                    continue
                if session_id and not self._request_matches_session(active_id, session_id):
                    continue
                event.set()
                cancelled.append(active_id)
        if not cancelled:
            return {"success": False, "error_code": "SYSCALL_NOT_FOUND", "correlation_id": correlation_id, "session_id": session_id}
        for active_id in cancelled:
            self._append_jsonl(
                self.paths.events,
                {
                    "type": "human_cancel_requested",
                    "correlation_id": active_id,
                    "session_id": session_id,
                    "created_at": utc_now(),
                },
            )
        return {"success": True, "status": "cancel_requested", "cancelled": cancelled}

    def record_response(self, correlation_id: str, answer: str, *, operator_id: str = "", reason: str = "") -> dict[str, Any]:
        if not correlation_id:
            return {"success": False, "error_code": "HUMAN_CORRELATION_ID_REQUIRED"}
        record = {
            "type": "human_response",
            "correlation_id": correlation_id,
            "answer": answer,
            "operator_id": operator_id,
            "reason": reason,
            "created_at": utc_now(),
        }
        self._append_jsonl(self.paths.responses, record)
        return {"success": True, "correlation_id": correlation_id, "response_path": str(self.paths.responses)}

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = sorted(self._active)
        status = {
            "success": True,
            "state": "ready",
            "backend": "file_human_queue",
            "root": str(self.paths.root),
            "request_path": str(self.paths.requests),
            "response_path": str(self.paths.responses),
            "active": active,
            "pending_count": self._pending_count(),
            "last_error": self._last_error,
        }
        contract = human_operator_contract(status)
        status.update(
            {
                "validate_config": contract["validate_config"],
                "health": contract["health"],
                "capabilities": contract["capabilities"],
                "error_code": contract["error_code"],
                "missing": contract["missing"],
                "details": contract["details"],
                "implemented_modes": contract["implemented_modes"],
                "available_modes": contract["available_modes"],
                "unsupported_modes": contract["unsupported_modes"],
                "reserved_modes": contract["reserved_modes"],
            }
        )
        return status

    def _find_response(self, correlation_id: str) -> dict[str, Any] | None:
        for record in reversed(self._read_jsonl(self.paths.responses)):
            if record.get("correlation_id") == correlation_id:
                return record
        return None

    def _request_matches_session(self, correlation_id: str, session_id: str) -> bool:
        for record in reversed(self._read_jsonl(self.paths.requests)):
            if record.get("correlation_id") == correlation_id:
                return record.get("session_id") == session_id
        return False

    def _pending_count(self) -> int:
        closed = {str(record.get("correlation_id")) for record in self._read_jsonl(self.paths.responses)}
        closed.update(
            str(record.get("correlation_id"))
            for record in self._read_jsonl(self.paths.events)
            if record.get("type") in {"human_answered", "human_cancelled", "human_timeout"}
        )
        return sum(1 for record in self._read_jsonl(self.paths.requests) if str(record.get("correlation_id")) not in closed)

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError as exc:
            self._last_error = str(exc)
            raise

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    records.append(parsed)
        except (OSError, json.JSONDecodeError) as exc:
            self._last_error = str(exc)
            return []
        return records
