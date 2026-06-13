from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def monotonic_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class KernelSyscallStatus:
    CREATED = "created"
    ACTIVE = "active"
    QUEUED = "queued"
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class KernelSyscall:
    """AIOS-style syscall object adapted for AgenticOS.

    AIOS models syscalls as objects with identity, status, source/target,
    priority, timing metrics, and response slots. This version keeps that
    contract but uses only stdlib types so it is safe to ship inside
    ``/opt/agentic/agentic_os/kernel``.
    """

    agent_name: str
    target: str
    operation_type: str
    params: dict[str, Any] = field(default_factory=dict)
    syscall_id: str = field(default_factory=lambda: monotonic_id("ksc"))
    source: str = ""
    priority: int = 0
    status: str = KernelSyscallStatus.CREATED
    response: Any = None
    error_code: str = ""
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    ended_at: str | None = None
    time_limit_s: float | None = None

    @classmethod
    def create(
        cls,
        agent_name: str,
        target: str,
        operation_type: str,
        params: dict[str, Any] | None = None,
        priority: int = 0,
        source: str = "",
    ) -> "KernelSyscall":
        return cls(
            agent_name=agent_name,
            target=target,
            operation_type=operation_type,
            params=dict(params or {}),
            priority=priority,
            source=source or agent_name,
        )

    def mark_active(self) -> None:
        self.status = KernelSyscallStatus.ACTIVE

    def mark_queued(self) -> None:
        self.status = KernelSyscallStatus.QUEUED

    def mark_started(self) -> None:
        self.status = KernelSyscallStatus.EXECUTING
        self.started_at = self.started_at or utc_now()

    def finish(self, response: Any = None, status: str = KernelSyscallStatus.DONE) -> None:
        self.response = response
        self.status = status
        self.ended_at = utc_now()

    def fail(self, error_code: str, response: Any = None) -> None:
        self.error_code = error_code
        self.finish(response=response, status=KernelSyscallStatus.FAILED)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

