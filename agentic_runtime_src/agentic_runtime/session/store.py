from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import SessionRecord


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def session_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.json"

    def syscalls_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "syscalls.jsonl"

    def save(self, record: SessionRecord) -> SessionRecord:
        path = self.session_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        return record

    def get(self, session_id: str) -> SessionRecord | None:
        path = self.session_path(session_id)
        if not path.exists():
            return None
        return SessionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def require(self, session_id: str) -> SessionRecord:
        record = self.get(session_id)
        if record is None:
            raise KeyError(f"session not found: {session_id}")
        return record

    def list(self, limit: int | None = None) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        for path in sorted(self.root.glob("sess_*/session.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            records.append(SessionRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            if limit is not None and len(records) >= limit:
                break
        return records

    def append_syscall(self, session_id: str, record: dict[str, Any]) -> None:
        path = self.syscalls_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def read_syscalls(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        path = self.syscalls_path(session_id)
        if not path.exists():
            return []
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if limit is not None:
            lines = lines[-limit:]
        return [json.loads(line) for line in lines]
