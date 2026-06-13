from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from agentic_runtime.types import new_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    TERMINAL = {COMPLETED, FAILED, CANCELLED}


@dataclass
class SessionRecord:
    session_id: str
    app_id: str
    status: str
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    task: dict[str, Any] = field(default_factory=dict)
    current_skill: str = ""
    result: dict[str, Any] | None = None
    error_code: str = ""
    stop_requested: bool = False
    mock: bool = True

    @classmethod
    def create(cls, app_id: str, task: dict[str, Any] | None = None, mock: bool = True) -> "SessionRecord":
        return cls(
            session_id=new_id("sess"),
            app_id=app_id,
            status=SessionStatus.QUEUED,
            created_at=utc_now(),
            task=dict(task or {}),
            mock=mock,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionRecord":
        return cls(
            session_id=str(data["session_id"]),
            app_id=str(data["app_id"]),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            task=dict(data.get("task") or {}),
            current_skill=str(data.get("current_skill") or ""),
            result=data.get("result"),
            error_code=str(data.get("error_code") or ""),
            stop_requested=bool(data.get("stop_requested", False)),
            mock=bool(data.get("mock", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
