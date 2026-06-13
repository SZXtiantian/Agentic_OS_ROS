from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class AuditRecord:
    audit_id: str
    timestamp: str
    app_id: str
    session_id: str
    skill_name: str
    args: dict[str, Any]
    permission_result: str
    safety_result: str
    resource_lock_result: str
    backend: str
    status: str
    error_code: str
    duration_ms: int


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._counter = self._initial_counter()

    def _initial_counter(self) -> int:
        if not self.path.exists():
            return 0
        count = 0
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def next_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"audit_{self._counter:06d}"

    def write(self, record: AuditRecord | dict[str, Any]) -> str:
        data = record.__dict__ if isinstance(record, AuditRecord) else dict(record)
        audit_id = str(data.get("audit_id") or self.next_id())
        data["audit_id"] = audit_id
        data.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")
        return audit_id

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records = []
        for line in lines[-limit:]:
            if line.strip():
                records.append(json.loads(line))
        return records
