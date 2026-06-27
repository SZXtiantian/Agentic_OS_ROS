from __future__ import annotations

from threading import RLock
from typing import Any

from agentic_os.kernel.system_call.models import monotonic_id, utc_now

from .errors import AGENT_NOT_FOUND, AgentLifecycleError
from .models import AgentResourceHandle, AgentResourceState


class AgentResourceRegistry:
    def __init__(self, event_sink=None) -> None:
        self._handles: dict[str, AgentResourceHandle] = {}
        self._lock = RLock()
        self.event_sink = event_sink

    def register(
        self,
        *,
        agent_id: str,
        resource_type: str,
        resource_id: str,
        backend: str = "",
        session_id: str = "",
        skill_call_id: str = "",
        syscall_id: str = "",
        lease_id: str = "",
        metadata: dict[str, Any] | None = None,
        handle_id: str = "",
    ) -> AgentResourceHandle:
        handle = AgentResourceHandle(
            handle_id=handle_id or monotonic_id("arh"),
            agent_id=agent_id,
            resource_type=resource_type,
            resource_id=resource_id,
            backend=backend,
            session_id=session_id,
            skill_call_id=skill_call_id,
            syscall_id=syscall_id,
            lease_id=lease_id,
            acquired_at=utc_now(),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._handles[handle.handle_id] = handle
            self._emit("agent.resource_registered", handle)
            return handle

    def get(self, handle_id: str) -> AgentResourceHandle | None:
        with self._lock:
            return self._handles.get(handle_id)

    def require(self, handle_id: str) -> AgentResourceHandle:
        handle = self.get(handle_id)
        if handle is None:
            raise AgentLifecycleError(AGENT_NOT_FOUND, f"agent resource handle not found: {handle_id}")
        return handle

    def list_by_agent(self, agent_id: str, *, active_only: bool = False) -> list[AgentResourceHandle]:
        with self._lock:
            handles = [handle for handle in self._handles.values() if handle.agent_id == agent_id]
            if active_only:
                handles = [handle for handle in handles if handle.is_active()]
            return sorted(handles, key=lambda handle: (handle.acquired_at, handle.handle_id))

    def list_active_by_agent(self, agent_id: str) -> list[AgentResourceHandle]:
        return self.list_by_agent(agent_id, active_only=True)

    def mark_release_pending(self, handle_id: str) -> AgentResourceHandle:
        with self._lock:
            handle = self.require(handle_id)
            if handle.state != AgentResourceState.RELEASED:
                handle.mark_release_pending(utc_now())
                self._emit("agent.resource_release_pending", handle)
            return handle

    def mark_released(self, handle_id: str) -> AgentResourceHandle:
        with self._lock:
            handle = self.require(handle_id)
            handle.mark_released(utc_now())
            self._emit("agent.resource_released", handle)
            return handle

    def mark_release_failed(self, handle_id: str, error_code: str, message: str) -> AgentResourceHandle:
        with self._lock:
            handle = self.require(handle_id)
            handle.mark_release_failed(error_code, message)
            self._emit("agent.resource_release_failed", handle, error_code=error_code)
            return handle

    def unregister(self, handle_id: str) -> AgentResourceHandle | None:
        with self._lock:
            return self._handles.pop(handle_id, None)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            handles = sorted(self._handles.values(), key=lambda handle: (handle.acquired_at, handle.handle_id))
            return {
                "active_count": sum(1 for handle in handles if handle.is_active()),
                "release_pending_count": sum(1 for handle in handles if handle.state == AgentResourceState.RELEASE_PENDING),
                "release_failed_count": sum(1 for handle in handles if handle.state == AgentResourceState.RELEASE_FAILED),
                "items": [handle.to_dict() for handle in handles],
            }

    def _emit(self, event_type: str, handle: AgentResourceHandle, **metadata: Any) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(
                event_type,
                agent_id=handle.agent_id,
                handle_id=handle.handle_id,
                resource_type=handle.resource_type,
                resource_id=handle.resource_id,
                state=handle.state,
                **metadata,
            )
