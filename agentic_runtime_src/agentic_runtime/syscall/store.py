from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_runtime.session.store import SessionStore


class SyscallStore:
    def __init__(self, session_root: Path) -> None:
        self.session_store = SessionStore(session_root)

    def append(self, session_id: str, record: dict[str, Any]) -> None:
        self.session_store.append_syscall(session_id, record)

    def list(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self.session_store.read_syscalls(session_id, limit=limit)
