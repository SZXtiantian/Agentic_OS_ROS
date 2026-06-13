from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_os.kernel.context import ContextManager as KernelContextManager

from .models import ContextSnapshot


class ContextManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.kernel = KernelContextManager(root)

    def snapshot(self, session_id: str, app_id: str, **kwargs: Any) -> ContextSnapshot:
        self.kernel.snapshot(session_id, app_id, **kwargs)
        return ContextSnapshot(session_id=session_id, app_id=app_id, **kwargs)

    def recover(self, session_id: str) -> ContextSnapshot | None:
        try:
            kernel_snapshot = self.kernel.recover(session_id)
        except (KeyError, TypeError, ValueError):
            return self._recover_legacy(session_id)
        if kernel_snapshot is None:
            return None
        return ContextSnapshot(
            session_id=kernel_snapshot.session_id,
            app_id=kernel_snapshot.agent_name,
            **kernel_snapshot.state,
        )

    def _path(self, session_id: str) -> Path:
        return self.root / session_id / "context.json"

    def _recover_legacy(self, session_id: str) -> ContextSnapshot | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ContextSnapshot(**data)
