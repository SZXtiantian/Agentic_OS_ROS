from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable

from agentic_os.kernel.hooks import KernelQueueStore

from .factory import create_syscall as create_typed_syscall
from .models import KernelSyscall, KernelSyscallStatus
from .schema import KernelQuery, KernelResponse

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

    def __init__(self, queue_store: KernelQueueStore | None = None, default_timeout_s: float = 60.0) -> None:
        self._handlers: dict[str, SyscallHandler] = {}
        self._lock = Lock()
        self._pid_lock = Lock()
        self._next_pid_value = 0
        self.queue_store = queue_store or KernelQueueStore()
        self.default_timeout_s = default_timeout_s

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

    def execute_request(
        self,
        agent_name: str,
        query: KernelQuery,
        timeout_s: float | None = None,
    ) -> SyscallExecutionResult:
        syscall = create_typed_syscall(agent_name, query)
        started = time.monotonic()
        syscall.mark_active()
        syscall.set_pid(self._next_pid())
        syscall.set_created_time(time.time())
        syscall.mark_queued()
        queue_name = getattr(syscall, "queue_name", syscall.target)
        self.queue_store.add(queue_name, syscall)

        wait_timeout = self.default_timeout_s if timeout_s is None else timeout_s
        completed = syscall.wait(wait_timeout)
        ended = time.monotonic()
        if not completed:
            response = KernelResponse(False, error_code="KERNEL_SYSCALL_TIMEOUT")
            syscall.error_code = response.error_code
            syscall.finish(response=response, status=KernelSyscallStatus.TIMEOUT)
            return SyscallExecutionResult(
                syscall=syscall,
                response=response,
                success=False,
                error_code=response.error_code,
                started_monotonic=started,
                ended_monotonic=ended,
                metadata={"queue_name": queue_name, "pid": syscall.get_pid()},
            )

        response = syscall.get_response()
        success = self._response_success(syscall, response)
        error_code = self._response_error_code(syscall, response)
        return SyscallExecutionResult(
            syscall=syscall,
            response=response,
            success=success,
            error_code=error_code,
            started_monotonic=started,
            ended_monotonic=ended,
            metadata={"queue_name": queue_name, "pid": syscall.get_pid()},
        )

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

    def _next_pid(self) -> int:
        with self._pid_lock:
            self._next_pid_value += 1
            return self._next_pid_value

    def _response_success(self, syscall: KernelSyscall, response: Any) -> bool:
        if isinstance(response, KernelResponse):
            return response.success
        if isinstance(response, dict) and "success" in response:
            return bool(response["success"])
        return syscall.status == KernelSyscallStatus.DONE

    def _response_error_code(self, syscall: KernelSyscall, response: Any) -> str:
        if isinstance(response, KernelResponse):
            return response.error_code
        if isinstance(response, dict):
            return str(response.get("error_code", syscall.error_code))
        return syscall.error_code
