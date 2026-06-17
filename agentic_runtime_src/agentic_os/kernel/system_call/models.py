from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
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
    SUSPENDING = "suspending"
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
    pid: int | None = None
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    ended_at: str | None = None
    created_time: float = field(default_factory=time.time)
    start_time: float | None = None
    end_time: float | None = None
    time_limit_s: float | None = None
    event: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)

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
        self.set_status(KernelSyscallStatus.ACTIVE)

    def mark_queued(self) -> None:
        self.set_status(KernelSyscallStatus.QUEUED)

    def mark_started(self) -> None:
        self.set_status(KernelSyscallStatus.EXECUTING)
        self.started_at = self.started_at or utc_now()
        self.start_time = self.start_time or time.time()

    def finish(self, response: Any = None, status: str = KernelSyscallStatus.DONE) -> None:
        self.response = response
        self.set_status(status)
        self.ended_at = utc_now()
        self.end_time = self.end_time or time.time()
        self.event.set()

    def fail(self, error_code: str, response: Any = None) -> None:
        self.error_code = error_code
        self.finish(response=response, status=KernelSyscallStatus.FAILED)

    def wait(self, timeout_s: float | None = None) -> bool:
        return self.event.wait(timeout=timeout_s)

    def start(self) -> None:
        self.mark_started()

    def join(self, timeout_s: float | None = None) -> bool:
        return self.wait(timeout_s)

    def set_response(self, response: Any) -> None:
        self.response = response

    def get_response(self) -> Any:
        return self.response

    def set_status(self, status: str) -> None:
        self.status = status

    def get_status(self) -> str:
        return self.status

    def set_pid(self, pid: int) -> None:
        self.pid = pid

    def get_pid(self) -> int | None:
        return self.pid

    def set_created_time(self, created_time: float) -> None:
        self.created_time = created_time

    def get_created_time(self) -> float:
        return self.created_time

    def set_start_time(self, start_time: float) -> None:
        self.start_time = start_time

    def get_start_time(self) -> float:
        return self.start_time or 0.0

    def set_end_time(self, end_time: float) -> None:
        self.end_time = end_time

    def get_end_time(self) -> float:
        return self.end_time or 0.0

    def set_source(self, source: str) -> None:
        self.source = source

    def get_source(self) -> str:
        return self.source

    def set_target(self, target: str) -> None:
        self.target = target

    def get_target(self) -> str:
        return self.target

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "target": self.target,
            "operation_type": self.operation_type,
            "params": self.params,
            "syscall_id": self.syscall_id,
            "source": self.source,
            "priority": self.priority,
            "status": self.status,
            "response": self.response,
            "error_code": self.error_code,
            "pid": self.pid,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "created_time": self.created_time,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "time_limit_s": self.time_limit_s,
            "queue_name": getattr(self, "queue_name", ""),
        }
