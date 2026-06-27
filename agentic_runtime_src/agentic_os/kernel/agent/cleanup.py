from __future__ import annotations

from typing import Any

from agentic_os.kernel.system_call import KernelSyscall
from agentic_os.kernel.system_call.models import utc_now

from .errors import AGENT_RESOURCE_RELEASE_FAILED
from .models import AgentCleanupStatus, AgentControlBlock, AgentLifecycleResult, AgentResourceState
from .resources import AgentResourceRegistry
from .table import AgentTable


class RuntimeResourceReleaseAdapter:
    def __init__(self, runtime_server: Any | None) -> None:
        self.runtime_server = runtime_server

    def release_agent_resources(self, agent: AgentControlBlock, reason: str = "") -> dict[str, Any]:
        executor = getattr(self.runtime_server, "executor", None)
        manager = getattr(executor, "resource_manager", None)
        if manager is None:
            return {"success": False, "error_code": AGENT_RESOURCE_RELEASE_FAILED, "reason": "resource manager not configured"}
        if hasattr(manager, "release_by_agent") and agent.agent_id:
            manager.release_by_agent(agent.agent_id)
            return {"success": True, "released_by": "agent", "reason": reason}
        if hasattr(manager, "release_by_session") and agent.session_id:
            manager.release_by_session(agent.session_id)
            return {"success": True, "released_by": "session", "reason": reason}
        return {"success": False, "error_code": AGENT_RESOURCE_RELEASE_FAILED, "reason": "release_by_agent/release_by_session unavailable"}


class RuntimeCancellationAdapter:
    def __init__(self, runtime_server: Any | None) -> None:
        self.runtime_server = runtime_server

    def request_running_cancellation(self, agent: AgentControlBlock, reason: str = "") -> dict[str, Any]:
        manager = self._manager()
        if manager is None:
            return {"success": False, "error_code": "CANCELLATION_MANAGER_UNAVAILABLE", "reason": "cancellation manager not configured"}
        if hasattr(manager, "cancel_session"):
            manager.cancel_session(agent.session_id)
            return {"success": True, "session_id": agent.session_id, "reason": reason}
        return {"success": False, "error_code": "CANCELLATION_MANAGER_UNAVAILABLE", "reason": "cancel_session unavailable"}

    def clear_agent_runtime_state(self, agent: AgentControlBlock, reason: str = "") -> dict[str, Any]:
        manager = self._manager()
        if manager is None:
            return {"success": True, "session_id": agent.session_id, "reason": reason}
        if hasattr(manager, "clear_session"):
            manager.clear_session(agent.session_id)
        return {"success": True, "session_id": agent.session_id, "reason": reason}

    def _manager(self):
        executor = getattr(self.runtime_server, "executor", None)
        return getattr(executor, "cancellation_manager", None)


class AgentCleanupManager:
    def __init__(
        self,
        *,
        resource_registry: AgentResourceRegistry,
        agent_table: AgentTable | None = None,
        queue_store=None,
        event_sink=None,
        audit_logger=None,
    ) -> None:
        self.resource_registry = resource_registry
        self.agent_table = agent_table
        self.queue_store = queue_store
        self.event_sink = event_sink
        self.audit_logger = audit_logger
        self._resource_release_adapters: list[Any] = []
        self._cancellation_adapters: list[Any] = []
        self._held_syscalls_by_agent: dict[str, list[KernelSyscall]] = {}

    def register_resource_release_adapter(self, adapter) -> None:
        self._resource_release_adapters.append(adapter)

    def register_cancellation_adapter(self, adapter) -> None:
        self._cancellation_adapters.append(adapter)

    def held_syscalls_for_agent(self, agent_id: str) -> list[KernelSyscall]:
        return list(self._held_syscalls_by_agent.get(agent_id, []))

    def hold_queued_syscalls(self, agent: AgentControlBlock, reason: str = "") -> list[KernelSyscall]:
        if self.queue_store is None:
            return []
        held = list(self.queue_store.hold_by_agent(agent.agent_id, reason=reason))
        if not held:
            return []
        self._held_syscalls_by_agent.setdefault(agent.agent_id, []).extend(held)
        for syscall in held:
            if self.agent_table is not None:
                self.agent_table.mark_syscall_held(agent.agent_id, syscall.syscall_id)
            self._emit("agent.syscall_held", agent, syscall_id=syscall.syscall_id, reason=reason)
        return held

    def resume_held_syscalls(self, agent: AgentControlBlock, reason: str = "") -> list[str]:
        held = self._held_syscalls_by_agent.pop(agent.agent_id, [])
        if not held or self.queue_store is None:
            return []
        resumed = list(self.queue_store.requeue_many(held, reason=reason))
        if self.agent_table is not None:
            resumed_set = set(resumed)

            def mutator(acb: AgentControlBlock) -> None:
                acb.held_syscall_ids = [syscall_id for syscall_id in acb.held_syscall_ids if syscall_id not in resumed_set]
                acb.touch()

            self.agent_table.update(agent.agent_id, mutator)
        for syscall_id in resumed:
            self._emit("agent.syscall_resumed", agent, syscall_id=syscall_id, reason=reason)
        return resumed

    def cancel_queued_and_held_syscalls(self, agent: AgentControlBlock, reason: str = "") -> list[KernelSyscall]:
        cancelled: list[KernelSyscall] = []
        if self.queue_store is not None:
            cancelled.extend(self.queue_store.cancel_by_agent(agent.agent_id, reason=reason))
        held = self._held_syscalls_by_agent.pop(agent.agent_id, [])
        for syscall in held:
            syscall.cancel(reason)
            syscall.event.set()
            cancelled.append(syscall)
        for syscall in cancelled:
            if self.agent_table is not None:
                self.agent_table.detach_syscall(agent.agent_id, syscall.syscall_id)
            self._emit("agent.syscall_cancelled", agent, syscall_id=syscall.syscall_id, reason=reason)
        return cancelled

    def request_running_cancellation(self, agent: AgentControlBlock, reason: str = "") -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for adapter in self._cancellation_adapters:
            try:
                if hasattr(adapter, "request_running_cancellation"):
                    results.append(dict(adapter.request_running_cancellation(agent, reason=reason)))
            except Exception as exc:
                results.append({"success": False, "error_code": "CANCELLATION_ADAPTER_FAILED", "reason": str(exc)})
        return results

    def release_agent_resources(self, agent: AgentControlBlock, reason: str = "") -> dict[str, list[str]]:
        active = self.resource_registry.list_active_by_agent(agent.agent_id)
        if not active:
            return {"released_resources": [], "pending_resources": [], "failed_resources": []}
        for handle in active:
            if handle.state != AgentResourceState.RELEASED:
                self.resource_registry.mark_release_pending(handle.handle_id)

        release_result = self._run_resource_release_adapters(agent, reason)
        released: list[str] = []
        failed: list[str] = []
        if release_result.get("success"):
            for handle in active:
                self.resource_registry.mark_released(handle.handle_id)
                released.append(handle.handle_id)
        else:
            error_code = str(release_result.get("error_code") or AGENT_RESOURCE_RELEASE_FAILED)
            message = str(release_result.get("reason") or "resource release failed")
            for handle in active:
                self.resource_registry.mark_release_failed(handle.handle_id, error_code, message)
                failed.append(handle.handle_id)
        return {"released_resources": released, "pending_resources": [], "failed_resources": failed}

    def clear_agent_runtime_state(self, agent: AgentControlBlock, reason: str = "") -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for adapter in self._cancellation_adapters:
            try:
                if hasattr(adapter, "clear_agent_runtime_state"):
                    results.append(dict(adapter.clear_agent_runtime_state(agent, reason=reason)))
            except Exception as exc:
                results.append({"success": False, "error_code": "RUNTIME_STATE_CLEAR_FAILED", "reason": str(exc)})
        return results

    def mark_cleanup_started(self, agent: AgentControlBlock) -> None:
        agent.cleanup_status = AgentCleanupStatus.RUNNING
        agent.cleanup_started_at = agent.cleanup_started_at or utc_now()
        agent.touch()
        self._emit("agent.cleanup_started", agent)

    def mark_cleanup_completed(self, agent: AgentControlBlock) -> None:
        agent.cleanup_status = AgentCleanupStatus.COMPLETED
        agent.cleanup_completed_at = agent.cleanup_completed_at or utc_now()
        agent.touch()
        self._emit("agent.cleanup_completed", agent)

    def mark_cleanup_failed(self, agent: AgentControlBlock, reason: str = "") -> None:
        agent.cleanup_status = AgentCleanupStatus.FAILED
        agent.cleanup_completed_at = agent.cleanup_completed_at or utc_now()
        agent.touch()
        self._emit("agent.cleanup_failed", agent, reason=reason)

    def cleanup_agent(
        self,
        agent: AgentControlBlock,
        *,
        reason: str,
        cancel_queued: bool = False,
        request_running_cancellation: bool = False,
    ) -> AgentLifecycleResult:
        if agent.cleanup_status == AgentCleanupStatus.COMPLETED:
            return AgentLifecycleResult.ok(agent)
        self.mark_cleanup_started(agent)
        cancelled: list[KernelSyscall] = []
        if cancel_queued:
            cancelled = self.cancel_queued_and_held_syscalls(agent, reason=reason)
        if request_running_cancellation:
            self.request_running_cancellation(agent, reason=reason)
        resources = self.release_agent_resources(agent, reason=reason)
        self.clear_agent_runtime_state(agent, reason=reason)
        if resources["failed_resources"]:
            self.mark_cleanup_failed(agent, reason=AGENT_RESOURCE_RELEASE_FAILED)
        else:
            self.mark_cleanup_completed(agent)
        return AgentLifecycleResult.ok(
            agent,
            cancelled_syscalls=[syscall.syscall_id for syscall in cancelled],
            released_resources=resources["released_resources"],
            pending_resources=resources["pending_resources"],
            failed_resources=resources["failed_resources"],
        )

    def _run_resource_release_adapters(self, agent: AgentControlBlock, reason: str) -> dict[str, Any]:
        if not self._resource_release_adapters:
            return {"success": False, "error_code": AGENT_RESOURCE_RELEASE_FAILED, "reason": "resource release adapter not configured"}
        last_error: dict[str, Any] = {}
        for adapter in self._resource_release_adapters:
            try:
                if hasattr(adapter, "release_agent_resources"):
                    result = dict(adapter.release_agent_resources(agent, reason=reason))
                else:
                    result = dict(adapter.release(agent, reason=reason))
            except Exception as exc:
                result = {"success": False, "error_code": AGENT_RESOURCE_RELEASE_FAILED, "reason": str(exc)}
            if result.get("success"):
                return result
            last_error = result
        return last_error or {"success": False, "error_code": AGENT_RESOURCE_RELEASE_FAILED, "reason": "resource release failed"}

    def _emit(self, event_type: str, agent: AgentControlBlock, **metadata: Any) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(
                event_type,
                agent_id=agent.agent_id,
                app_id=agent.app_id,
                session_id=agent.session_id,
                status=agent.status,
                **metadata,
            )
