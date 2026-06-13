from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call import KernelSyscall, KernelSyscallStatus

from agentic_runtime.session.models import utc_now
from agentic_runtime.types import new_id


class SyscallStatus:
    QUEUED = KernelSyscallStatus.QUEUED
    ACTIVE = KernelSyscallStatus.ACTIVE
    EXECUTING = KernelSyscallStatus.EXECUTING
    DONE = KernelSyscallStatus.DONE
    FAILED = KernelSyscallStatus.FAILED
    REJECTED = KernelSyscallStatus.REJECTED
    CANCELLED = KernelSyscallStatus.CANCELLED
    TIMEOUT = KernelSyscallStatus.TIMEOUT


@dataclass
class AgenticSyscall:
    syscall_id: str
    app_id: str
    session_id: str
    name: str
    args: dict[str, Any]
    status: str = SyscallStatus.QUEUED
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    ended_at: str | None = None
    result: dict[str, Any] | None = None
    error_code: str = ""
    audit_id: str = ""

    @classmethod
    def create(cls, app_id: str, session_id: str, name: str, args: dict[str, Any]) -> "AgenticSyscall":
        return cls(syscall_id=new_id("syscall"), app_id=app_id, session_id=session_id, name=name, args=dict(args))

    def mark_started(self, status: str = SyscallStatus.EXECUTING) -> None:
        self.status = status
        self.started_at = self.started_at or utc_now()

    def finish(
        self,
        status: str,
        result: dict[str, Any] | None = None,
        error_code: str = "",
        audit_id: str = "",
    ) -> None:
        self.status = status
        self.result = result
        self.error_code = error_code
        self.audit_id = audit_id
        self.ended_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_kernel_syscall(self) -> KernelSyscall:
        syscall = KernelSyscall.create(
            self.app_id,
            self.name.split(".", 1)[0] if "." in self.name else self.name,
            self.name,
            self.args,
        )
        syscall.syscall_id = self.syscall_id
        syscall.status = self.status
        syscall.created_at = self.created_at
        syscall.started_at = self.started_at
        syscall.ended_at = self.ended_at
        syscall.response = self.result
        syscall.error_code = self.error_code
        return syscall


@dataclass
class SkillSyscall(AgenticSyscall):
    skill_name: str = ""
    permission_result: str = "not_checked"
    safety_result: str = "not_required"
    resource_lock_result: str = "not_required"

    @classmethod
    def create(cls, app_id: str, session_id: str, skill_name: str, args: dict[str, Any]) -> "SkillSyscall":
        return cls(
            syscall_id=new_id("syscall"),
            app_id=app_id,
            session_id=session_id,
            name=skill_name,
            skill_name=skill_name,
            args=dict(args),
        )
