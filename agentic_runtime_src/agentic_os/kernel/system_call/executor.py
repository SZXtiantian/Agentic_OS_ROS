from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable

from .models import KernelSyscall, KernelSyscallStatus

SyscallHandler = Callable[[KernelSyscall], Any]


@dataclass
class SyscallExecutionResult:
    syscall: KernelSyscall
    response: Any = None
    success: bool = True
    error_code: str = ""
    started_monotonic: float = 0.0
    ended_monotonic: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        if not self.started_monotonic or not self.ended_monotonic:
            return 0
        return int((self.ended_monotonic - self.started_monotonic) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "syscall": self.syscall.to_dict(),
            "response": self.response,
            "success": self.success,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


class SyscallExecutor:
    """Target-based syscall dispatcher.

    This is the AgenticOS port of AIOS's ``SyscallExecutor``. AIOS pushed calls
    into global queues by type; this implementation keeps the same target
    separation while letting runtime code register explicit handlers.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, SyscallHandler] = {}
        self._lock = Lock()

    def register(self, target: str, handler: SyscallHandler) -> None:
        with self._lock:
            self._handlers[target] = handler

    def unregister(self, target: str) -> None:
        with self._lock:
            self._handlers.pop(target, None)

    def create_syscall(
        self,
        agent_name: str,
        target: str,
        operation_type: str,
        params: dict[str, Any] | None = None,
    ) -> KernelSyscall:
        return KernelSyscall.create(agent_name, target, operation_type, params)

    def execute(self, syscall: KernelSyscall) -> SyscallExecutionResult:
        with self._lock:
            handler = self._handlers.get(syscall.target)
        if handler is None:
            syscall.status = KernelSyscallStatus.REJECTED
            syscall.error_code = "KERNEL_SYSCALL_TARGET_NOT_FOUND"
            syscall.ended_at = syscall.ended_at or syscall.created_at
            return SyscallExecutionResult(syscall=syscall, success=False, error_code=syscall.error_code)

        started = time.monotonic()
        syscall.mark_started()
        try:
            response = handler(syscall)
            syscall.finish(response=response)
            return SyscallExecutionResult(
                syscall=syscall,
                response=response,
                started_monotonic=started,
                ended_monotonic=time.monotonic(),
            )
        except TimeoutError as exc:
            syscall.finish(response={"reason": str(exc)}, status=KernelSyscallStatus.TIMEOUT)
            syscall.error_code = "KERNEL_SYSCALL_TIMEOUT"
            return SyscallExecutionResult(
                syscall=syscall,
                response=syscall.response,
                success=False,
                error_code=syscall.error_code,
                started_monotonic=started,
                ended_monotonic=time.monotonic(),
            )
        except Exception as exc:
            syscall.fail("KERNEL_SYSCALL_HANDLER_FAILED", {"reason": str(exc)})
            return SyscallExecutionResult(
                syscall=syscall,
                response=syscall.response,
                success=False,
                error_code=syscall.error_code,
                started_monotonic=started,
                ended_monotonic=time.monotonic(),
            )

