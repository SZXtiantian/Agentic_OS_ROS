from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable

from agentic_os.kernel.hooks import KernelEventSink, KernelQueueStore

from .factory import create_syscall as create_typed_syscall
from .models import KernelSyscall, KernelSyscallStatus
from .schema import KernelQuery, KernelResponse

SyscallHandler = Callable[[KernelSyscall], Any]
AGENT_ID_REQUIRED = "AGENT_ID_REQUIRED"


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

    def __init__(
        self,
        queue_store: KernelQueueStore | None = None,
        default_timeout_s: float = 60.0,
        event_sink: KernelEventSink | None = None,
        agent_lifecycle=None,
    ) -> None:
        self._handlers: dict[str, SyscallHandler] = {}
        self._lock = Lock()
        self._pid_lock = Lock()
        self._next_pid_value = 0
        self.queue_store = queue_store or KernelQueueStore()
        self.default_timeout_s = default_timeout_s
        self.event_sink = event_sink
        self.agent_lifecycle = agent_lifecycle

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
        started = time.monotonic()
        metadata = dict(getattr(query, "metadata", {}) or {})
        agent_id = str(metadata.get("agent_id") or "")
        if self.agent_lifecycle is not None:
            if not agent_id and not metadata.get("kernel_internal"):
                return self._reject_without_agent(agent_name, query, started)
            if agent_id:
                decision = self.agent_lifecycle.admit_syscall(
                    agent_id=agent_id,
                    operation_type=query.operation_type,
                )
                if not decision.success:
                    return self._reject_agent_syscall(agent_name, query, decision, started, agent_id=agent_id)

        syscall = create_typed_syscall(agent_name, query)
        if self.agent_lifecycle is not None and agent_id:
            bind = self.agent_lifecycle.bind_syscall(agent_id, syscall)
            if not bind.success:
                syscall.reject(bind.error_code, str(bind.response_message or bind.metadata.get("reason", "")))
                return SyscallExecutionResult(
                    syscall=syscall,
                    response=bind,
                    success=False,
                    error_code=bind.error_code,
                    started_monotonic=started,
                    ended_monotonic=time.monotonic(),
                    metadata={"agent_id": agent_id, "syscall_id": syscall.syscall_id},
                )

        syscall.mark_active()
        syscall.set_pid(self._next_pid())
        syscall.set_created_time(time.time())
        self._emit("syscall.created", syscall, queue_name=getattr(syscall, "queue_name", syscall.target))
        syscall.mark_queued()
        queue_name = getattr(syscall, "queue_name", syscall.target)
        self.queue_store.add(queue_name, syscall)

        wait_timeout = self.default_timeout_s if timeout_s is None else timeout_s
        syscall.time_limit_s = wait_timeout
        completed = syscall.wait(wait_timeout)
        ended = time.monotonic()
        if not completed:
            response = KernelResponse.error("KERNEL_SYSCALL_TIMEOUT")
            if syscall.status in {
                KernelSyscallStatus.CREATED,
                KernelSyscallStatus.ACTIVE,
                KernelSyscallStatus.QUEUED,
                KernelSyscallStatus.SUSPENDING,
                KernelSyscallStatus.SUSPENDED,
                KernelSyscallStatus.RESUMING,
            }:
                syscall.timeout(response=response)
                self._emit("syscall.timeout", syscall, queue_name=queue_name, error_code=response.error_code)
            else:
                self._emit("syscall.wait_timeout", syscall, queue_name=queue_name, error_code=response.error_code)
            return SyscallExecutionResult(
                syscall=syscall,
                response=response,
                success=False,
                error_code=response.error_code,
                started_monotonic=started,
                ended_monotonic=ended,
                metadata={"queue_name": queue_name, "pid": syscall.get_pid(), "wait_timeout": True},
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
            syscall.reject("KERNEL_SYSCALL_TARGET_NOT_FOUND", f"target not found: {syscall.target}")
            return SyscallExecutionResult(syscall=syscall, success=False, error_code=syscall.error_code)

        started = time.monotonic()
        syscall.mark_started()
        try:
            response = handler(syscall)
            invalid_error = self._invalid_response_error_code(response)
            if invalid_error:
                syscall.fail(invalid_error, response)
            elif self._explicit_failure(response):
                syscall.fail(self._response_error_code(syscall, response) or "KERNEL_SYSCALL_REJECTED", response)
            else:
                syscall.finish(response=response)
            return SyscallExecutionResult(
                syscall=syscall,
                response=response,
                success=syscall.status == KernelSyscallStatus.DONE,
                error_code=syscall.error_code,
                started_monotonic=started,
                ended_monotonic=time.monotonic(),
            )
        except TimeoutError as exc:
            syscall.timeout(response={"success": False, "error_code": "KERNEL_SYSCALL_TIMEOUT", "reason": str(exc)})
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

    def cancel_request(self, syscall_id: str) -> KernelResponse:
        if not syscall_id:
            response = KernelResponse.error("SYSCALL_NOT_FOUND", metadata={"reason": "syscall_id required"})
            self._emit_cancel_result(syscall_id, response)
            return response

        removed = self.queue_store.remove(syscall_id)
        if removed is None:
            response = KernelResponse.error("SYSCALL_NOT_FOUND", metadata={"syscall_id": syscall_id})
            self._emit_cancel_result(syscall_id, response)
            return response

        response = KernelResponse.ok(
            {"cancelled": [syscall_id]},
            metadata={
                "syscall_id": syscall_id,
                "queue_name": getattr(removed, "queue_name", removed.target),
                "pid": removed.get_pid(),
                "status": removed.status,
            },
            data={"cancelled": [syscall_id]},
        )
        self._emit_cancel_result(syscall_id, response)
        return response

    def _next_pid(self) -> int:
        with self._pid_lock:
            self._next_pid_value += 1
            return self._next_pid_value

    def _response_success(self, syscall: KernelSyscall, response: Any) -> bool:
        if self._invalid_response_error_code(response):
            return False
        if isinstance(response, KernelResponse):
            return response.success
        if isinstance(response, dict) and "success" in response:
            return response["success"]
        return syscall.status == KernelSyscallStatus.DONE

    def _response_error_code(self, syscall: KernelSyscall, response: Any) -> str:
        invalid_error = self._invalid_response_error_code(response)
        if invalid_error:
            return invalid_error
        if isinstance(response, KernelResponse):
            return response.error_code
        if isinstance(response, dict):
            return str(response.get("error_code", syscall.error_code))
        return syscall.error_code

    def _explicit_failure(self, response: Any) -> bool:
        if isinstance(response, KernelResponse):
            return isinstance(response.success, bool) and response.success is False
        if isinstance(response, dict) and "success" in response:
            return isinstance(response["success"], bool) and response["success"] is False
        return False

    def _invalid_response_error_code(self, response: Any) -> str:
        if isinstance(response, KernelResponse) and not isinstance(response.success, bool):
            return "KERNEL_RESULT_INVALID"
        if isinstance(response, dict) and "success" in response and not isinstance(response["success"], bool):
            return "KERNEL_RESULT_INVALID"
        return ""

    def _emit(self, event_type: str, syscall: KernelSyscall, **metadata: Any) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(
                event_type,
                syscall_id=syscall.syscall_id,
                agent_name=syscall.agent_name,
                operation_type=syscall.operation_type,
                status=syscall.status,
                **metadata,
            )

    def _emit_cancel_result(self, syscall_id: str, response: KernelResponse) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(
                "syscall.cancel_request",
                syscall_id=syscall_id,
                success=response.success,
                error_code=response.error_code,
            )

    def _reject_without_agent(self, agent_name: str, query: KernelQuery, started: float) -> SyscallExecutionResult:
        syscall = create_typed_syscall(agent_name, query)
        response = KernelResponse.error(
            AGENT_ID_REQUIRED,
            metadata={"reason": "agent_id is required for ordinary kernel syscall"},
        )
        syscall.reject(AGENT_ID_REQUIRED, "agent_id is required for ordinary kernel syscall")
        return SyscallExecutionResult(
            syscall=syscall,
            response=response,
            success=False,
            error_code=AGENT_ID_REQUIRED,
            started_monotonic=started,
            ended_monotonic=time.monotonic(),
            metadata={"syscall_id": syscall.syscall_id},
        )

    def _reject_agent_syscall(
        self,
        agent_name: str,
        query: KernelQuery,
        decision: KernelResponse,
        started: float,
        *,
        agent_id: str,
    ) -> SyscallExecutionResult:
        syscall = create_typed_syscall(agent_name, query)
        syscall.reject(decision.error_code, str(decision.response_message or decision.metadata.get("reason", "")))
        metadata = {"agent_id": agent_id, "syscall_id": syscall.syscall_id, **dict(decision.metadata or {})}
        return SyscallExecutionResult(
            syscall=syscall,
            response=decision,
            success=False,
            error_code=decision.error_code,
            started_monotonic=started,
            ended_monotonic=time.monotonic(),
            metadata=metadata,
        )
