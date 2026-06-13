from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ContextSnapshot:
    session_id: str
    agent_name: str
    state: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


class ContextManager:
    """Snapshot/recover context manager based on AIOS context restoration."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def snapshot(self, session_id: str, agent_name: str, **state: Any) -> ContextSnapshot:
        snapshot = ContextSnapshot(session_id=session_id, agent_name=agent_name, state=dict(state))
        path = self._path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return snapshot

    def recover(self, session_id: str) -> ContextSnapshot | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ContextSnapshot(**data)

    def _path(self, session_id: str) -> Path:
        return self.root / session_id / "context.json"

