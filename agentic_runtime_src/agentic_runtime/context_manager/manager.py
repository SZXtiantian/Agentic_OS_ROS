from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.context import ContextManager as KernelContextManager
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelSyscall

from agentic_runtime.errors import AgenticRuntimeError

from .models import ContextSnapshot


class ContextManager:
    def __init__(
        self,
        root: Path,
        *,
        access_manager: AccessManager | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.root = root
        self.access_manager = access_manager
        self.kernel = KernelContextManager(root, access_manager=access_manager, event_sink=event_sink)

    def snapshot(self, session_id: str, app_id: str, **kwargs: Any) -> ContextSnapshot:
        if self.access_manager is None:
            self.kernel.snapshot(session_id, app_id, **kwargs)
        else:
            response = self.kernel.address_request(
                KernelSyscall.create(
                    app_id,
                    "context",
                    "ctx_snapshot",
                    {
                        "session_id": session_id,
                        "checkpoint": "runtime_session",
                        "state": dict(kwargs),
                    },
                )
            )
            if not response.success:
                raise AgenticRuntimeError(
                    response.error_code or "CONTEXT_SNAPSHOT_FAILED",
                    str(response.metadata.get("reason") or "runtime context snapshot failed"),
                )
        return ContextSnapshot(session_id=session_id, app_id=app_id, **kwargs)

    def recover(self, session_id: str) -> ContextSnapshot | None:
        if self.access_manager is not None:
            return self._recover_via_syscall(session_id)
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

    def _recover_via_syscall(self, session_id: str) -> ContextSnapshot | None:
        owner = self.kernel._latest_owner_for_session(session_id)
        if not owner:
            return self._recover_legacy(session_id)
        response = self.kernel.address_request(
            KernelSyscall.create(
                owner,
                "context",
                "ctx_recover",
                {
                    "session_id": session_id,
                    "checkpoint": "runtime_session",
                },
            )
        )
        if response.success:
            payload = response.data if isinstance(response.data, dict) else dict(response.response_message or {})
            return ContextSnapshot(
                session_id=str(payload.get("session_id") or session_id),
                app_id=str(payload.get("owner_agent") or owner),
                **dict(payload.get("state") or {}),
            )
        if response.error_code == "CONTEXT_NOT_FOUND":
            return self._recover_legacy(session_id)
        raise AgenticRuntimeError(
            response.error_code or "CONTEXT_RECOVER_FAILED",
            str(response.metadata.get("reason") or "runtime context recover failed"),
        )
