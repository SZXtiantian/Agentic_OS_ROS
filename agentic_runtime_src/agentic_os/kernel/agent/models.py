from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call.models import monotonic_id, utc_now


class AgentStatus:
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    SUSPEND_REQUESTED = "suspend_requested"
    SUSPENDED = "suspended"
    KILL_REQUESTED = "kill_requested"
    KILLING = "killing"
    EXITED = "exited"
    FAILED = "failed"
    CRASHED = "crashed"
    KILLED = "killed"
    REAPED = "reaped"

    TERMINAL = {EXITED, FAILED, CRASHED, KILLED}
    DEAD = {EXITED, FAILED, CRASHED, KILLED, REAPED}
    ACCEPTS_NEW_SYSCALL = {READY, RUNNING}
    CAN_SUSPEND = {READY, RUNNING}
    CAN_RESUME = {SUSPENDED}
    CAN_KILL = {
        CREATED,
        READY,
        RUNNING,
        SUSPEND_REQUESTED,
        SUSPENDED,
        KILL_REQUESTED,
        KILLING,
    }
    CAN_REAP = TERMINAL


class AgentExitKind:
    NONE = ""
    SUCCESS = "success"
    FAILURE = "failure"
    CRASH = "crash"
    KILL = "kill"


class AgentCleanupStatus:
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentResourceState:
    ACQUIRED = "acquired"
    RELEASE_PENDING = "release_pending"
    RELEASED = "released"
    RELEASE_FAILED = "release_failed"


@dataclass
class AgentResourceHandle:
    handle_id: str
    agent_id: str
    resource_type: str
    resource_id: str
    backend: str = ""
    session_id: str = ""
    skill_call_id: str = ""
    syscall_id: str = ""
    lease_id: str = ""
    state: str = AgentResourceState.ACQUIRED
    acquired_at: str = ""
    release_requested_at: str | None = None
    released_at: str | None = None
    release_error_code: str = ""
    release_error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_release_pending(self, ts: str) -> None:
        self.state = AgentResourceState.RELEASE_PENDING
        self.release_requested_at = ts

    def mark_released(self, ts: str) -> None:
        self.state = AgentResourceState.RELEASED
        self.released_at = ts
        self.release_error_code = ""
        self.release_error_message = ""

    def mark_release_failed(self, error_code: str, message: str) -> None:
        self.state = AgentResourceState.RELEASE_FAILED
        self.release_error_code = error_code
        self.release_error_message = message

    def is_active(self) -> bool:
        return self.state in {
            AgentResourceState.ACQUIRED,
            AgentResourceState.RELEASE_PENDING,
            AgentResourceState.RELEASE_FAILED,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentControlBlock:
    agent_id: str
    app_id: str
    session_id: str
    agent_name: str = ""
    parent_agent_id: str = ""
    created_by: str = "session_runner"
    status: str = AgentStatus.CREATED
    previous_status: str = ""
    priority: int = 0
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    updated_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    reaped_at: str | None = None
    heartbeat_at: str | None = None
    owned_syscall_ids: list[str] = field(default_factory=list)
    running_syscall_ids: list[str] = field(default_factory=list)
    held_syscall_ids: list[str] = field(default_factory=list)
    resource_handle_ids: list[str] = field(default_factory=list)
    suspend_reason: str = ""
    kill_reason: str = ""
    cancellation_requested: bool = False
    cleanup_status: str = AgentCleanupStatus.NOT_REQUIRED
    cleanup_started_at: str | None = None
    cleanup_completed_at: str | None = None
    exit_kind: str = AgentExitKind.NONE
    exit_code: int | None = None
    exit_reason: str = ""
    error_code: str = ""
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        app_id: str,
        session_id: str,
        *,
        agent_name: str = "",
        parent_agent_id: str = "",
        created_by: str = "session_runner",
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
        agent_id: str = "",
    ) -> "AgentControlBlock":
        now = utc_now()
        return cls(
            agent_id=agent_id or monotonic_id("agent"),
            app_id=app_id,
            session_id=session_id,
            agent_name=agent_name or app_id,
            parent_agent_id=parent_agent_id,
            created_by=created_by,
            priority=priority,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )

    def is_terminal(self) -> bool:
        return self.status in AgentStatus.TERMINAL

    def is_dead(self) -> bool:
        return self.status in AgentStatus.DEAD

    def accepts_new_syscall(self) -> bool:
        return self.status in AgentStatus.ACCEPTS_NEW_SYSCALL

    def has_running_syscalls(self) -> bool:
        return bool(self.running_syscall_ids)

    def has_owned_syscalls(self) -> bool:
        return bool(self.owned_syscall_ids or self.running_syscall_ids or self.held_syscall_ids)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def heartbeat(self) -> None:
        now = utc_now()
        self.heartbeat_at = now
        self.updated_at = now

    def transition(self, new_status: str) -> None:
        self.previous_status = self.status
        self.status = new_status
        self.updated_at = utc_now()

    def mark_ready(self) -> None:
        self.transition(AgentStatus.READY)

    def mark_running(self) -> None:
        self.transition(AgentStatus.RUNNING)
        self.started_at = self.started_at or utc_now()

    def request_suspend(self, reason: str) -> None:
        self.suspend_reason = reason
        self.transition(AgentStatus.SUSPEND_REQUESTED)

    def mark_suspended(self) -> None:
        self.transition(AgentStatus.SUSPENDED)

    def mark_resumed(self) -> None:
        self.suspend_reason = ""
        self.transition(AgentStatus.READY)

    def request_kill(self, reason: str) -> None:
        self.kill_reason = reason
        self.cancellation_requested = True
        self.transition(AgentStatus.KILL_REQUESTED)

    def mark_killing(self) -> None:
        self.cancellation_requested = True
        self.cleanup_status = AgentCleanupStatus.RUNNING
        self.cleanup_started_at = self.cleanup_started_at or utc_now()
        self.transition(AgentStatus.KILLING)

    def mark_terminal(
        self,
        *,
        status: str,
        exit_kind: str,
        reason: str = "",
        error_code: str = "",
        error_message: str = "",
        exit_code: int | None = None,
    ) -> None:
        self.exit_kind = exit_kind
        self.exit_reason = reason
        self.error_code = error_code
        self.error_message = error_message
        self.exit_code = exit_code
        self.ended_at = self.ended_at or utc_now()
        self.transition(status)

    def attach_syscall(self, syscall_id: str) -> None:
        if syscall_id and syscall_id not in self.owned_syscall_ids:
            self.owned_syscall_ids.append(syscall_id)
            self.touch()

    def mark_syscall_running(self, syscall_id: str) -> None:
        self.attach_syscall(syscall_id)
        if syscall_id not in self.running_syscall_ids:
            self.running_syscall_ids.append(syscall_id)
        if syscall_id in self.held_syscall_ids:
            self.held_syscall_ids.remove(syscall_id)
        self.touch()

    def mark_syscall_held(self, syscall_id: str) -> None:
        self.attach_syscall(syscall_id)
        if syscall_id in self.running_syscall_ids:
            self.running_syscall_ids.remove(syscall_id)
        if syscall_id not in self.held_syscall_ids:
            self.held_syscall_ids.append(syscall_id)
        self.touch()

    def detach_syscall(self, syscall_id: str) -> None:
        for collection in (
            self.owned_syscall_ids,
            self.running_syscall_ids,
            self.held_syscall_ids,
        ):
            if syscall_id in collection:
                collection.remove(syscall_id)
        self.touch()

    def attach_resource(self, handle_id: str) -> None:
        if handle_id and handle_id not in self.resource_handle_ids:
            self.resource_handle_ids.append(handle_id)
            self.touch()

    def detach_resource(self, handle_id: str) -> None:
        if handle_id in self.resource_handle_ids:
            self.resource_handle_ids.remove(handle_id)
            self.touch()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentLifecycleResult:
    success: bool
    agent_id: str = ""
    status: str = ""
    error_code: str = ""
    reason: str = ""
    held_syscalls: list[str] = field(default_factory=list)
    resumed_syscalls: list[str] = field(default_factory=list)
    cancelled_syscalls: list[str] = field(default_factory=list)
    released_resources: list[str] = field(default_factory=list)
    pending_resources: list[str] = field(default_factory=list)
    failed_resources: list[str] = field(default_factory=list)
    cleanup_status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, agent: AgentControlBlock, **kwargs: Any) -> "AgentLifecycleResult":
        return cls(
            success=True,
            agent_id=agent.agent_id,
            status=agent.status,
            cleanup_status=agent.cleanup_status,
            **kwargs,
        )

    @classmethod
    def error(
        cls,
        error_code: str,
        *,
        agent_id: str = "",
        status: str = "",
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "AgentLifecycleResult":
        return cls(
            success=False,
            agent_id=agent_id,
            status=status,
            error_code=error_code,
            reason=reason,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
