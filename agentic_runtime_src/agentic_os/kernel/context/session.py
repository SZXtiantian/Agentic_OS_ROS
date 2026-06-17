from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .manager import utc_now


@dataclass
class SessionContextSnapshot:
    session_id: str
    agent_name: str
    task: dict[str, Any] = field(default_factory=dict)
    place: str = ""
    current_skill: str = ""
    world_snapshot_ref: str = ""
    audit_correlation_id: str = ""
    recovery_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SessionContextManager:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def snapshot(
        self,
        session_id: str,
        agent_name: str,
        task: dict[str, Any] | None = None,
        **metadata: Any,
    ) -> SessionContextSnapshot:
        snapshot = SessionContextSnapshot(
            session_id=session_id,
            agent_name=agent_name,
            task=dict(task or {}),
            place=str(metadata.get("place", "")),
            current_skill=str(metadata.get("current_skill", "")),
            world_snapshot_ref=str(metadata.get("world_snapshot_ref", "")),
            audit_correlation_id=str(metadata.get("audit_correlation_id", "")),
            recovery_metadata=dict(metadata.get("recovery_metadata") or {}),
        )
        path = self._path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return snapshot

    def recover(self, session_id: str) -> SessionContextSnapshot | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        return SessionContextSnapshot(**json.loads(path.read_text(encoding="utf-8")))

    def _path(self, session_id: str) -> Path:
        return self.root / session_id / "session_context.json"
