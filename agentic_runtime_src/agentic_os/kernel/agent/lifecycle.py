from __future__ import annotations

from typing import Any

from agentic_os.kernel.system_call import KernelResponse, KernelSyscall

from .cleanup import AgentCleanupManager
from .errors import (
    AGENT_CLEANUP_INCOMPLETE,
    AGENT_CRASHED,
    AGENT_HAS_ACTIVE_SYSCALLS,
    AGENT_ID_REQUIRED,
    AGENT_KILLED,
    AGENT_KILL_REQUESTED,
    AGENT_NOT_FOUND,
    AGENT_NOT_RUNNABLE,
    AGENT_REAPED,
    AGENT_REAP_FORBIDDEN,
    AGENT_RESOURCE_RELEASE_FAILED,
    AGENT_SUSPENDED,
    AGENT_TERMINAL,
    AGENT_TRANSITION_INVALID,
    AgentLifecycleError,
)
from .models import AgentCleanupStatus, AgentControlBlock, AgentExitKind, AgentLifecycleResult, AgentResourceState, AgentStatus
from .resources import AgentResourceRegistry
from .table import AgentTable


class AgentLifecycleManager:
    def __init__(
        self,
        *,
        agent_table: AgentTable,
        resource_registry: AgentResourceRegistry,
        cleanup_manager: AgentCleanupManager,
        event_sink=None,
        audit_logger=None,
    ) -> None:
        self.agent_table = agent_table
        self.resource_registry = resource_registry
        self.cleanup_manager = cleanup_manager
        self.event_sink = event_sink
        self.audit_logger = audit_logger

    def create_agent(
        self,
        *,
        app_id: str,
        session_id: str,
        agent_name: str = "",
        parent_agent_id: str = "",
        created_by: str = "kernel_service",
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
        agent_id: str = "",
    ) -> AgentControlBlock:
        return self.agent_table.create(
            app_id=app_id,
            session_id=session_id,
            agent_name=agent_name,
            parent_agent_id=parent_agent_id,
            created_by=created_by,
            priority=priority,
            metadata=metadata,
            agent_id=agent_id,
        )

    def create_agent_for_session(
        self,
        *,
        app_id: str,
        session_id: str,
        agent_name: str = "",
        parent_agent_id: str = "",
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
        agent_id: str = "",
    ) -> AgentControlBlock:
        return self.agent_table.create(
            app_id=app_id,
            session_id=session_id,
            agent_name=agent_name or app_id,
            parent_agent_id=parent_agent_id,
            created_by="session_runner",
            priority=priority,
            metadata=metadata,
            agent_id=agent_id,
        )

    def start_agent(self, agent_id: str, reason: str = "start") -> AgentLifecycleResult:
        try:
            agent = self.agent_table.require(agent_id)
            if agent.status in {AgentStatus.READY, AgentStatus.RUNNING}:
                return AgentLifecycleResult.ok(agent)
            if agent.status != AgentStatus.CREATED:
                return AgentLifecycleResult.error(AGENT_NOT_RUNNABLE, agent_id=agent_id, status=agent.status, reason=reason)
            agent.mark_ready()
            self._emit("agent.ready", agent, reason=reason)
            return AgentLifecycleResult.ok(agent)
        except AgentLifecycleError as exc:
            return AgentLifecycleResult.error(exc.error_code, agent_id=agent_id, reason=exc.reason)

    def get_agent(self, agent_id: str) -> AgentControlBlock:
        return self.agent_table.require(agent_id, include_reaped=True)

    def list_agents(self, include_reaped: bool = False) -> list[AgentControlBlock]:
        return self.agent_table.list(include_reaped=include_reaped)

    def admit_syscall(self, *, agent_id: str, operation_type: str, syscall_id: str = "") -> KernelResponse:
        if not agent_id:
            return KernelResponse.error(AGENT_ID_REQUIRED, metadata={"operation_type": operation_type, "syscall_id": syscall_id})
        try:
            agent = self.agent_table.require(agent_id)
        except AgentLifecycleError as exc:
            return KernelResponse.error(exc.error_code, metadata={"agent_id": agent_id, "operation_type": operation_type})
        if agent.status in AgentStatus.ACCEPTS_NEW_SYSCALL:
            return KernelResponse.ok({"agent_id": agent_id, "operation_type": operation_type})
        if agent.status == AgentStatus.CREATED:
            return KernelResponse.error(AGENT_NOT_RUNNABLE, metadata={"agent_id": agent_id, "status": agent.status})
        if agent.status in {AgentStatus.SUSPEND_REQUESTED, AgentStatus.SUSPENDED}:
            return KernelResponse.error(AGENT_SUSPENDED, metadata={"agent_id": agent_id, "status": agent.status})
        if agent.status in {AgentStatus.KILL_REQUESTED, AgentStatus.KILLING}:
            return KernelResponse.error(AGENT_KILL_REQUESTED, metadata={"agent_id": agent_id, "status": agent.status})
        if agent.status in AgentStatus.TERMINAL:
            return KernelResponse.error(AGENT_TERMINAL, metadata={"agent_id": agent_id, "status": agent.status})
        if agent.status == AgentStatus.REAPED:
            return KernelResponse.error(AGENT_REAPED, metadata={"agent_id": agent_id, "status": agent.status})
        return KernelResponse.error(AGENT_NOT_RUNNABLE, metadata={"agent_id": agent_id, "status": agent.status})

    def bind_syscall(self, agent_id: str, syscall: KernelSyscall) -> KernelResponse:
        decision = self.admit_syscall(agent_id=agent_id, operation_type=syscall.operation_type, syscall_id=syscall.syscall_id)
        if not decision.success:
            return decision
        syscall.agent_id = agent_id
        syscall.aid = agent_id
        self.agent_table.attach_syscall(agent_id, syscall.syscall_id)
        self._emit("agent.syscall_bound", self.agent_table.require(agent_id), syscall_id=syscall.syscall_id)
        return KernelResponse.ok({"agent_id": agent_id, "syscall_id": syscall.syscall_id})

    def on_syscall_started(self, syscall: KernelSyscall) -> None:
        agent_id = str(getattr(syscall, "agent_id", "") or getattr(syscall, "aid", "") or "")
        if not agent_id:
            return
        try:
            agent = self.agent_table.require(agent_id)
        except AgentLifecycleError:
            return
        if agent.status in AgentStatus.DEAD:
            return

        def mutator(acb: AgentControlBlock) -> None:
            acb.mark_syscall_running(syscall.syscall_id)
            if acb.status == AgentStatus.READY:
                acb.mark_running()

        agent = self.agent_table.update(agent_id, mutator)
        self._emit("agent.syscall_started", agent, syscall_id=syscall.syscall_id)

    def on_syscall_finished(self, syscall: KernelSyscall) -> None:
        agent_id = str(getattr(syscall, "agent_id", "") or getattr(syscall, "aid", "") or "")
        if not agent_id:
            return
        try:
            agent = self.agent_table.require(agent_id)
        except AgentLifecycleError:
            return

        def mutator(acb: AgentControlBlock) -> None:
            acb.detach_syscall(syscall.syscall_id)
            if acb.status == AgentStatus.RUNNING and not acb.running_syscall_ids:
                acb.mark_ready()
            elif acb.status == AgentStatus.SUSPEND_REQUESTED and not acb.running_syscall_ids:
                acb.mark_suspended()

        agent = self.agent_table.update(agent_id, mutator)
        self._emit("agent.syscall_finished", agent, syscall_id=syscall.syscall_id, syscall_status=syscall.status)

    def register_resource(
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
    ) -> str:
        self.agent_table.require(agent_id)
        handle = self.resource_registry.register(
            agent_id=agent_id,
            resource_type=resource_type,
            resource_id=resource_id,
            backend=backend,
            session_id=session_id,
            skill_call_id=skill_call_id,
            syscall_id=syscall_id,
            lease_id=lease_id,
            metadata=metadata,
            handle_id=handle_id,
        )
        self.agent_table.attach_resource(agent_id, handle.handle_id)
        return handle.handle_id

    def mark_resource_released(self, handle_id: str) -> None:
        self.resource_registry.mark_released(handle_id)

    def mark_resource_release_failed(self, handle_id: str, error_code: str, message: str) -> None:
        self.resource_registry.mark_release_failed(handle_id, error_code, message)

    def unregister_resource(self, handle_id: str) -> None:
        handle = self.resource_registry.unregister(handle_id)
        if handle is not None:
            try:
                self.agent_table.detach_resource(handle.agent_id, handle.handle_id)
            except AgentLifecycleError:
                pass

    def suspend_agent(self, agent_id: str, *, reason: str = "operator_requested") -> AgentLifecycleResult:
        try:
            agent = self.agent_table.require(agent_id)
            if agent.status == AgentStatus.SUSPENDED:
                return AgentLifecycleResult.ok(agent)
            if agent.status not in AgentStatus.CAN_SUSPEND:
                return AgentLifecycleResult.error(AGENT_TRANSITION_INVALID, agent_id=agent_id, status=agent.status, reason=reason)
            agent.request_suspend(reason)
            self._emit("agent.suspend_requested", agent, reason=reason)
            held = self.cleanup_manager.hold_queued_syscalls(agent, reason=reason)
            if not agent.running_syscall_ids:
                agent.mark_suspended()
                self._emit("agent.suspended", agent, reason=reason)
            return AgentLifecycleResult.ok(agent, held_syscalls=[syscall.syscall_id for syscall in held])
        except AgentLifecycleError as exc:
            return AgentLifecycleResult.error(exc.error_code, agent_id=agent_id, reason=exc.reason)

    def resume_agent(self, agent_id: str, *, reason: str = "operator_requested") -> AgentLifecycleResult:
        try:
            agent = self.agent_table.require(agent_id)
            if agent.status != AgentStatus.SUSPENDED:
                return AgentLifecycleResult.error(AGENT_TRANSITION_INVALID, agent_id=agent_id, status=agent.status, reason=reason)
            agent.mark_resumed()
            resumed = self.cleanup_manager.resume_held_syscalls(agent, reason=reason)
            self._emit("agent.resumed", agent, reason=reason)
            return AgentLifecycleResult.ok(agent, resumed_syscalls=resumed)
        except AgentLifecycleError as exc:
            return AgentLifecycleResult.error(exc.error_code, agent_id=agent_id, reason=exc.reason)

    def kill_agent(self, agent_id: str, *, reason: str = "operator_requested", force: bool = False) -> AgentLifecycleResult:
        try:
            agent = self.agent_table.require(agent_id)
            if agent.status == AgentStatus.KILLED:
                return AgentLifecycleResult.ok(agent)
            if agent.status not in AgentStatus.CAN_KILL:
                return AgentLifecycleResult.error(AGENT_TRANSITION_INVALID, agent_id=agent_id, status=agent.status, reason=reason)
            agent.request_kill(reason)
            self._emit("agent.kill_requested", agent, reason=reason, force=force)
            agent.mark_killing()
            self._emit("agent.killing", agent, reason=reason, force=force)
            cleanup = self.cleanup_manager.cleanup_agent(agent, reason=reason, cancel_queued=True, request_running_cancellation=True)
            agent.mark_terminal(
                status=AgentStatus.KILLED,
                exit_kind=AgentExitKind.KILL,
                reason=reason,
                error_code=AGENT_KILLED,
            )
            self._emit("agent.killed", agent, reason=reason, force=force)
            return AgentLifecycleResult.ok(
                agent,
                cancelled_syscalls=cleanup.cancelled_syscalls,
                released_resources=cleanup.released_resources,
                pending_resources=cleanup.pending_resources,
                failed_resources=cleanup.failed_resources,
            )
        except AgentLifecycleError as exc:
            return AgentLifecycleResult.error(exc.error_code, agent_id=agent_id, reason=exc.reason)

    def exit_agent(self, agent_id: str, *, reason: str = "app_completed", exit_code: int = 0) -> AgentLifecycleResult:
        return self._terminal_cleanup(
            agent_id,
            status=AgentStatus.EXITED,
            exit_kind=AgentExitKind.SUCCESS,
            reason=reason,
            error_code="",
            exit_code=exit_code,
            cancel_queued=False,
            request_running_cancellation=False,
            event_type="agent.exited",
        )

    def fail_agent(self, agent_id: str, *, reason: str, error_code: str, exit_code: int = 1) -> AgentLifecycleResult:
        return self._terminal_cleanup(
            agent_id,
            status=AgentStatus.FAILED,
            exit_kind=AgentExitKind.FAILURE,
            reason=reason,
            error_code=error_code,
            exit_code=exit_code,
            cancel_queued=False,
            request_running_cancellation=False,
            event_type="agent.failed",
        )

    def crash_agent(self, agent_id: str, *, reason: str, error_code: str = AGENT_CRASHED) -> AgentLifecycleResult:
        return self._terminal_cleanup(
            agent_id,
            status=AgentStatus.CRASHED,
            exit_kind=AgentExitKind.CRASH,
            reason=reason,
            error_code=error_code,
            exit_code=1,
            cancel_queued=True,
            request_running_cancellation=True,
            event_type="agent.crashed",
        )

    def reap_agent(self, agent_id: str, *, reason: str = "reap", remove_from_live: bool = True) -> AgentLifecycleResult:
        try:
            agent = self.agent_table.require(agent_id)
            if agent.status not in AgentStatus.CAN_REAP:
                return AgentLifecycleResult.error(AGENT_REAP_FORBIDDEN, agent_id=agent_id, status=agent.status, reason=reason)
            if agent.running_syscall_ids:
                return AgentLifecycleResult.error(
                    AGENT_HAS_ACTIVE_SYSCALLS,
                    agent_id=agent_id,
                    status=agent.status,
                    reason=reason,
                    metadata={"running_syscall_ids": list(agent.running_syscall_ids)},
                )
            if agent.cleanup_status not in {AgentCleanupStatus.COMPLETED, AgentCleanupStatus.FAILED}:
                return AgentLifecycleResult.error(AGENT_CLEANUP_INCOMPLETE, agent_id=agent_id, status=agent.status, reason=reason)
            active = [
                handle
                for handle in self.resource_registry.list_by_agent(agent_id)
                if handle.state not in {AgentResourceState.RELEASED, AgentResourceState.RELEASE_FAILED}
            ]
            if active:
                return AgentLifecycleResult.error(
                    AGENT_RESOURCE_RELEASE_FAILED,
                    agent_id=agent_id,
                    status=agent.status,
                    reason=reason,
                    metadata={"resource_handle_ids": [handle.handle_id for handle in active]},
                )
            if remove_from_live:
                agent = self.agent_table.move_to_tombstone(agent_id)
            else:
                agent.transition(AgentStatus.REAPED)
                self._emit("agent.reaped", agent, reason=reason)
            return AgentLifecycleResult.ok(agent)
        except AgentLifecycleError as exc:
            return AgentLifecycleResult.error(exc.error_code, agent_id=agent_id, reason=exc.reason)

    def status(self, include_reaped: bool = False) -> dict[str, Any]:
        return self.agent_table.snapshot(include_reaped=include_reaped)

    def _terminal_cleanup(
        self,
        agent_id: str,
        *,
        status: str,
        exit_kind: str,
        reason: str,
        error_code: str,
        exit_code: int,
        cancel_queued: bool,
        request_running_cancellation: bool,
        event_type: str,
    ) -> AgentLifecycleResult:
        try:
            agent = self.agent_table.require(agent_id)
            if agent.status in AgentStatus.TERMINAL:
                return AgentLifecycleResult.ok(agent)
            if agent.status == AgentStatus.REAPED:
                return AgentLifecycleResult.error(AGENT_REAPED, agent_id=agent_id, status=agent.status, reason=reason)
            cleanup = self.cleanup_manager.cleanup_agent(
                agent,
                reason=reason,
                cancel_queued=cancel_queued,
                request_running_cancellation=request_running_cancellation,
            )
            agent.mark_terminal(
                status=status,
                exit_kind=exit_kind,
                reason=reason,
                error_code=error_code,
                exit_code=exit_code,
            )
            self._emit(event_type, agent, reason=reason)
            return AgentLifecycleResult.ok(
                agent,
                cancelled_syscalls=cleanup.cancelled_syscalls,
                released_resources=cleanup.released_resources,
                pending_resources=cleanup.pending_resources,
                failed_resources=cleanup.failed_resources,
            )
        except AgentLifecycleError as exc:
            return AgentLifecycleResult.error(exc.error_code, agent_id=agent_id, reason=exc.reason)

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
