from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any

from agentic_runtime.types import new_id

from .models import TaskLogRetentionReport, TaskRecord, utc_now
from .retention import select_records_for_retention


class TaskLogManager:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        retain_recent_n: int = 200,
        retain_failed_n: int = 50,
        retain_rejected_n: int = 50,
        max_task_log_bytes: int = 10_485_760,
        store_user_text: bool = True,
    ) -> None:
        self.root = Path(root or os.environ.get("AGENTIC_TASK_LOG_ROOT") or _default_root()).expanduser()
        self.retain_recent_n = retain_recent_n
        self.retain_failed_n = retain_failed_n
        self.retain_rejected_n = retain_rejected_n
        self.max_task_log_bytes = max_task_log_bytes
        self.store_user_text = store_user_text
        self.path = self.root / "task_log.jsonl"
        self.recent_path = self.root / "recent_tasks.json"
        self.meta_path = self.root / "task_log.meta.json"
        self.plans_root = self.root / "plans"
        self._lock = Lock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.plans_root.mkdir(parents=True, exist_ok=True)

    def new_task_id(self) -> str:
        return new_id("task")

    def new_route_plan_id(self) -> str:
        return new_id("plan_route")

    def write_route_plan(self, route_plan: dict[str, Any]) -> Path:
        route_plan_id = str(route_plan.get("route_plan_id") or self.new_route_plan_id())
        path = self.plans_root / f"{_safe_name(route_plan_id)}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_small_json(route_plan), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        return path

    def create_task(self, user_text: str, route_plan: dict[str, Any], dispatcher_session_id: str) -> TaskRecord:
        now = utc_now()
        record = TaskRecord(
            schema_version="1.0",
            task_id=str(route_plan.get("task_id") or self.new_task_id()),
            created_at=now,
            updated_at=now,
            status="planned",
            user_text=user_text if self.store_user_text else "",
            user_text_hash=_hash_text(user_text),
            privacy_mode="store_text" if self.store_user_text else "hash_only",
            dispatcher_session_id=dispatcher_session_id,
            route_plan_id=str(route_plan.get("route_plan_id", "")),
            planner_mode=str(route_plan.get("planner_mode", "")),
            selected_app_id=str(route_plan.get("selected_app_id", "")),
            selected_agents=[],
            risk_class=str(route_plan.get("risk_class", "")),
            requires_robot_motion=bool(route_plan.get("requires_robot_motion", False)),
            needs_confirmation=bool(route_plan.get("needs_confirmation", False)),
            confirmation={
                "required": bool(route_plan.get("needs_confirmation", False)),
                "granted": False,
                "source": "",
            },
            result_summary={},
            detail_refs={"route_plan_path": str(self.plans_root / f"{_safe_name(str(route_plan.get('route_plan_id', '')))}.json")},
        )
        return self._append(record)

    def mark_running(self, task_id: str, selected_agents: list[dict[str, Any]]) -> TaskRecord:
        record = self.require(task_id)
        record.status = "running"
        record.updated_at = utc_now()
        record.selected_agents = list(selected_agents)
        return self._append(record)

    def attach_agent_session(self, task_id: str, agent_id: str, session_id: str, role: str = "primary_executor") -> TaskRecord:
        record = self.require(task_id)
        updated = False
        for item in record.selected_agents:
            if item.get("agent_id") == agent_id and item.get("role") == role:
                item["session_id"] = session_id
                item["status"] = "running"
                updated = True
        if not updated:
            record.selected_agents.append({"agent_id": agent_id, "role": role, "session_id": session_id, "status": "running"})
        record.updated_at = utc_now()
        return self._append(record)

    def complete_task(self, task_id: str, result_summary: dict[str, Any], detail_refs: dict[str, Any] | None = None) -> TaskRecord:
        record = self.require(task_id)
        record.status = str(result_summary.get("status") or "completed")
        record.updated_at = utc_now()
        record.result_summary = _small_json(dict(result_summary))
        if detail_refs:
            record.detail_refs.update(_small_json(dict(detail_refs)))
        for item in record.selected_agents:
            if not item.get("status") or item.get("status") in {"planned", "running"}:
                item["status"] = "completed" if record.status == "completed" else record.status
        return self._append(record)

    def fail_task(self, task_id: str, error_code: str, reason: str, detail_refs: dict[str, Any] | None = None) -> TaskRecord:
        record = self.require(task_id)
        record.status = "failed"
        record.updated_at = utc_now()
        record.error_code = error_code
        record.reason = reason
        record.result_summary = {"success": False, "error_code": error_code, "summary": reason}
        if detail_refs:
            record.detail_refs.update(_small_json(dict(detail_refs)))
        for item in record.selected_agents:
            if not item.get("status") or item.get("status") == "running":
                item["status"] = "failed"
        return self._append(record)

    def reject_task(self, task_id: str, error_code: str, reason: str, route_plan: dict[str, Any] | None = None) -> TaskRecord:
        record = self.require(task_id)
        record.status = "rejected"
        record.updated_at = utc_now()
        record.error_code = error_code
        record.reason = reason
        record.result_summary = {"success": False, "error_code": error_code, "summary": reason}
        if route_plan is not None:
            record.detail_refs["route_plan_id"] = str(route_plan.get("route_plan_id", record.route_plan_id))
        return self._append(record)

    def list_recent(self, limit: int = 20) -> list[TaskRecord]:
        records = sorted(self._latest_records(), key=lambda item: item.updated_at, reverse=True)
        return records[:limit]

    def get(self, task_id: str) -> TaskRecord | None:
        for record in self._latest_records():
            if record.task_id == task_id:
                return record
        return None

    def require(self, task_id: str) -> TaskRecord:
        record = self.get(task_id)
        if record is None:
            raise KeyError(f"task not found: {task_id}")
        return record

    def compact(self, force: bool = False) -> TaskLogRetentionReport:
        records = self._read_all()
        before = len(records)
        should_compact = force or (self.path.exists() and self.path.stat().st_size > self.max_task_log_bytes)
        if not should_compact:
            return TaskLogRetentionReport(
                success=True,
                before_count=before,
                after_count=len(self._latest_records()),
                retained_recent_n=self.retain_recent_n,
                retained_failed_n=self.retain_failed_n,
                retained_rejected_n=self.retain_rejected_n,
                compacted=False,
                task_log_path=str(self.path),
            )
        retained = select_records_for_retention(
            records,
            retain_recent_n=self.retain_recent_n,
            retain_failed_n=self.retain_failed_n,
            retain_rejected_n=self.retain_rejected_n,
        )
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for record in retained:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        tmp.replace(self.path)
        self._write_recent(retained)
        self._write_meta(len(retained), compacted=True)
        return TaskLogRetentionReport(
            success=True,
            before_count=before,
            after_count=len(retained),
            retained_recent_n=self.retain_recent_n,
            retained_failed_n=self.retain_failed_n,
            retained_rejected_n=self.retain_rejected_n,
            compacted=True,
            task_log_path=str(self.path),
        )

    def _append(self, record: TaskRecord) -> TaskRecord:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            latest = self._latest_records_locked()
            self._write_recent(latest)
            self._write_meta(len(latest), compacted=False)
        if self.path.exists() and self.path.stat().st_size > self.max_task_log_bytes:
            self.compact()
        return record

    def _read_all(self) -> list[TaskRecord]:
        if not self.path.exists():
            return []
        records: list[TaskRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("task_id"):
                records.append(TaskRecord.from_dict(data))
        return records

    def _latest_records(self) -> list[TaskRecord]:
        with self._lock:
            return self._latest_records_locked()

    def _latest_records_locked(self) -> list[TaskRecord]:
        latest: OrderedDict[str, TaskRecord] = OrderedDict()
        for record in self._read_all():
            latest[record.task_id] = record
        return sorted(latest.values(), key=lambda item: item.updated_at, reverse=True)

    def _write_recent(self, records: list[TaskRecord]) -> None:
        data = [record.to_dict() for record in sorted(records, key=lambda item: item.updated_at, reverse=True)[: self.retain_recent_n]]
        tmp = self.recent_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.recent_path)

    def _write_meta(self, count: int, *, compacted: bool) -> None:
        data = {
            "schema_version": "1.0",
            "updated_at": utc_now(),
            "recent_count": count,
            "retain_recent_n": self.retain_recent_n,
            "retain_failed_n": self.retain_failed_n,
            "retain_rejected_n": self.retain_rejected_n,
            "max_task_log_bytes": self.max_task_log_bytes,
            "last_write_compacted": bool(compacted),
        }
        tmp = self.meta_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.meta_path)


def _default_root() -> Path:
    var_root = Path(os.environ.get("AGENTIC_VAR", "/opt/agentic/var")).expanduser()
    return var_root / "tasks"


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_name(value: str) -> str:
    text = str(value or "")
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    return safe.strip("._") or "task"


def _small_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _small_json(item) for key, item in value.items() if not _looks_large_key(str(key))}
    if isinstance(value, list):
        return [_small_json(item) for item in value[:200]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "...<truncated>"
    return value


def _looks_large_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in {"image_base64", "video_base64", "raw_pixels", "llm_context", "full_prompt"}
