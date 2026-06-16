from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    schema_version: str
    task_id: str
    created_at: str
    updated_at: str
    status: str
    user_text: str
    user_text_hash: str
    privacy_mode: str
    dispatcher_session_id: str
    route_plan_id: str
    planner_mode: str
    selected_app_id: str
    selected_agents: list[dict[str, Any]] = field(default_factory=list)
    risk_class: str = ""
    requires_robot_motion: bool = False
    needs_confirmation: bool = False
    confirmation: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    detail_refs: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskRecord":
        return cls(
            schema_version=str(data.get("schema_version", "1.0")),
            task_id=str(data["task_id"]),
            created_at=str(data.get("created_at", utc_now())),
            updated_at=str(data.get("updated_at", utc_now())),
            status=str(data.get("status", "planned")),
            user_text=str(data.get("user_text", "")),
            user_text_hash=str(data.get("user_text_hash", "")),
            privacy_mode=str(data.get("privacy_mode", "store_text")),
            dispatcher_session_id=str(data.get("dispatcher_session_id", "")),
            route_plan_id=str(data.get("route_plan_id", "")),
            planner_mode=str(data.get("planner_mode", "")),
            selected_app_id=str(data.get("selected_app_id", "")),
            selected_agents=list(data.get("selected_agents") or []),
            risk_class=str(data.get("risk_class", "")),
            requires_robot_motion=bool(data.get("requires_robot_motion", False)),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
            confirmation=dict(data.get("confirmation") or {}),
            result_summary=dict(data.get("result_summary") or {}),
            detail_refs=dict(data.get("detail_refs") or {}),
            error_code=str(data.get("error_code", "")),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskLogRetentionReport:
    success: bool
    before_count: int
    after_count: int
    retained_recent_n: int
    retained_failed_n: int
    retained_rejected_n: int
    compacted: bool
    task_log_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
