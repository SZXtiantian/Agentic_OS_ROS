from __future__ import annotations

import threading
import time
from typing import Any

from agentic_os.kernel.hooks import KernelEventSink, KernelQueueStore
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall, KernelSyscallStatus
from agentic_os.kernel.system_call.models import utc_now

from .lanes import DEFAULT_SCHEDULER_LANES, SchedulerLaneSpec


class BaseKernelScheduler:
    def __init__(
        self,
        queue_store: KernelQueueStore,
        managers: dict[str, Any],
        lanes: tuple[SchedulerLaneSpec, ...] = DEFAULT_SCHEDULER_LANES,
        log_mode: str = "console",
        poll_timeout_s: float = 0.05,
        event_sink: KernelEventSink | None = None,
        agent_lifecycle=None,
    ) -> None:
        self.queue_store = queue_store
        self.managers = managers
        self.lanes = lanes
        self.log_mode = log_mode
        self.poll_timeout_s = poll_timeout_s
        self.event_sink = event_sink
        self.agent_lifecycle = agent_lifecycle
        self.active = False
        self.processing_threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self.active:
                return
            self.active = True
            for lane in self.lanes:
                workers = max(1, lane.max_workers if lane.concurrent else 1)
                for index in range(workers):
                    thread_name = f"kernel-{lane.name}-{index}"
                    thread = threading.Thread(target=self.process_queue, args=(lane,), name=thread_name, daemon=True)
                    self.processing_threads[thread_name] = thread
                    thread.start()

    def stop(self, timeout_s: float = 5.0) -> None:
        with self._lock:
            self.active = False
            threads = list(self.processing_threads.items())
        deadline = time.monotonic() + timeout_s
        for _name, thread in threads:
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)
        with self._lock:
            self.processing_threads = {
                name: thread for name, thread in self.processing_threads.items() if thread.is_alive()
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            threads = {name: thread.is_alive() for name, thread in sorted(self.processing_threads.items())}
            active = self.active
        return {
            "active": active,
            "threads": threads,
            "queues": self.queue_store.snapshot(),
            "lanes": [lane.name for lane in self.lanes],
        }

    def process_queue(self, lane: SchedulerLaneSpec) -> None:
        while self.active:
            if lane.batchable:
                batch = self._collect_batch(lane)
                if batch:
                    self._execute_batch(lane, batch)
                continue
            syscall = self.queue_store.get(lane.queue_name, timeout_s=self.poll_timeout_s)
            if syscall is None:
                continue
            self._execute_syscall(lane, syscall)

    def _collect_batch(self, lane: SchedulerLaneSpec) -> list[KernelSyscall]:
        first = self.queue_store.get(lane.queue_name, timeout_s=lane.queue_timeout_s or self.poll_timeout_s)
        if first is None:
            return []
        batch = [first]
        deadline = time.monotonic() + (lane.batch_window_ms / 1000.0)
        while len(batch) < max(1, lane.max_batch_size):
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                break
            syscall = self.queue_store.get(lane.queue_name, timeout_s=remaining)
            if syscall is None:
                break
            batch.append(syscall)
        return batch

    def _execute_batch(self, lane: SchedulerLaneSpec, syscalls: list[KernelSyscall]) -> None:
        ready: list[KernelSyscall] = []
        for syscall in syscalls:
            if syscall.is_cancelled():
                self._emit("syscall.cancelled", syscall=syscall, queue_name=lane.queue_name)
                self._notify_syscall_finished(syscall)
                syscall.event.set()
                continue
            if syscall.is_expired():
                self._finish_syscall(
                    syscall,
                    KernelSyscallStatus.TIMEOUT,
                    KernelResponse.error("KERNEL_SYSCALL_TIMEOUT", metadata={"reason": "expired before batch execution"}),
                    error_code="KERNEL_SYSCALL_TIMEOUT",
                )
                self._emit("syscall.timeout", syscall=syscall, queue_name=lane.queue_name, error_code="KERNEL_SYSCALL_TIMEOUT")
                self._notify_syscall_finished(syscall)
                syscall.event.set()
                continue
            syscall.mark_started()
            self._notify_syscall_started(syscall)
            self._emit("syscall.started", syscall=syscall, queue_name=lane.queue_name)
            ready.append(syscall)
        if not ready:
            return

        manager_key = lane.manager_key or lane.queue_name
        manager = self.managers.get(manager_key) or self.managers.get(lane.queue_name)
        if manager is None:
            for syscall in ready:
                self._fail_syscall(syscall, "KERNEL_MANAGER_NOT_FOUND", f"manager not found for {manager_key}")
                self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
                self._notify_syscall_finished(syscall)
                syscall.event.set()
            return

        responses: list[Any] = []
        try:
            batch_started = time.monotonic()
            self._emit("manager.started", syscall=ready[0], queue_name=lane.queue_name, manager_key=manager_key, batch_size=len(ready))
            if hasattr(manager, "address_batch"):
                responses = list(manager.address_batch(ready))
            elif hasattr(manager, "complete_batch"):
                responses = list(manager.complete_batch([getattr(syscall, "query", None) for syscall in ready]))
            else:
                for syscall in ready:
                    self._execute_syscall(lane, syscall)
                return
        except TimeoutError as exc:
            for syscall in ready:
                self._fail_syscall(syscall, "KERNEL_MANAGER_TIMEOUT", str(exc))
                self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
                self._emit("manager.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code="KERNEL_MANAGER_TIMEOUT")
                self._notify_syscall_finished(syscall)
                syscall.event.set()
            return
        except Exception as exc:
            for syscall in ready:
                self._fail_syscall(syscall, "KERNEL_MANAGER_FAILED", str(exc))
                self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
                self._emit("manager.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code="KERNEL_MANAGER_FAILED")
                self._notify_syscall_finished(syscall)
                syscall.event.set()
            return

        for syscall, response in zip(ready, responses, strict=False):
            if self._response_success(response):
                self._finish_syscall(syscall, KernelSyscallStatus.DONE, response)
                self._emit("syscall.done", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key)
            else:
                self._finish_syscall(
                    syscall,
                    KernelSyscallStatus.FAILED,
                    response,
                    error_code=self._response_error_code(response) or "KERNEL_MANAGER_REJECTED",
                )
                self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
            self._notify_syscall_finished(syscall)
        if len(responses) < len(ready):
            for syscall in ready[len(responses) :]:
                self._fail_syscall(syscall, "KERNEL_MANAGER_FAILED", "batch manager returned too few responses")
                self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
                self._notify_syscall_finished(syscall)
        self._emit("manager.done", syscall=ready[0], queue_name=lane.queue_name, manager_key=manager_key, duration_ms=int((time.monotonic() - batch_started) * 1000), batch_size=len(ready))
        for syscall in ready:
            syscall.event.set()

    def _execute_syscall(self, lane: SchedulerLaneSpec, syscall: KernelSyscall) -> None:
        if syscall.is_cancelled():
            self._emit("syscall.cancelled", syscall=syscall, queue_name=lane.queue_name)
            self._notify_syscall_finished(syscall)
            syscall.event.set()
            return
        if syscall.is_expired():
            self._finish_syscall(
                syscall,
                KernelSyscallStatus.TIMEOUT,
                KernelResponse.error("KERNEL_SYSCALL_TIMEOUT", metadata={"reason": "expired before execution"}),
                error_code="KERNEL_SYSCALL_TIMEOUT",
            )
            self._emit("syscall.timeout", syscall=syscall, queue_name=lane.queue_name, error_code="KERNEL_SYSCALL_TIMEOUT")
            self._notify_syscall_finished(syscall)
            syscall.event.set()
            return
        manager_key = lane.manager_key or lane.queue_name
        manager = self.managers.get(manager_key) or self.managers.get(lane.queue_name)
        if manager is None:
            self._fail_syscall(syscall, "KERNEL_MANAGER_NOT_FOUND", f"manager not found for {manager_key}")
            self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
            self._notify_syscall_finished(syscall)
            syscall.event.set()
            return

        try:
            syscall.mark_started()
            self._notify_syscall_started(syscall)
            self._emit("syscall.started", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key)
            manager_started = time.monotonic()
            self._emit("manager.started", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key)
            if hasattr(manager, "address_request"):
                response = manager.address_request(syscall)
            else:
                response = manager(syscall)
            if self._response_success(response):
                self._finish_syscall(syscall, KernelSyscallStatus.DONE, response)
                self._emit("syscall.done", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key)
            else:
                self._finish_syscall(
                    syscall,
                    KernelSyscallStatus.FAILED,
                    response,
                    error_code=self._response_error_code(response) or "KERNEL_MANAGER_REJECTED",
                )
                self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
            self._emit("manager.done", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, duration_ms=int((time.monotonic() - manager_started) * 1000))
        except TimeoutError as exc:
            self._fail_syscall(syscall, "KERNEL_MANAGER_TIMEOUT", str(exc))
            self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
            self._emit("manager.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code="KERNEL_MANAGER_TIMEOUT")
            return
        except Exception as exc:
            self._fail_syscall(syscall, "KERNEL_MANAGER_FAILED", str(exc))
            self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
            self._emit("manager.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code="KERNEL_MANAGER_FAILED")
            return
        finally:
            if syscall.end_time is None:
                syscall.set_end_time(time.time())
            syscall.ended_at = syscall.ended_at or utc_now()
            self._notify_syscall_finished(syscall)
            syscall.event.set()

    def _fail_syscall(self, syscall: KernelSyscall, error_code: str, reason: str) -> None:
        self._finish_syscall(syscall, KernelSyscallStatus.FAILED, KernelResponse.error(error_code, metadata={"reason": reason}), error_code=error_code)

    def _finish_syscall(self, syscall: KernelSyscall, status: str, response: Any = None, error_code: str = "") -> None:
        syscall.response = response
        syscall.error_code = error_code
        syscall.set_status(status)
        syscall.ended_at = syscall.ended_at or utc_now()
        syscall.end_time = syscall.end_time or time.time()

    def _response_success(self, response: Any) -> bool:
        if self._invalid_response_error_code(response):
            return False
        if isinstance(response, KernelResponse):
            return response.success
        if isinstance(response, dict) and "success" in response:
            return response["success"]
        return True

    def _response_error_code(self, response: Any) -> str:
        invalid_error = self._invalid_response_error_code(response)
        if invalid_error:
            return invalid_error
        if isinstance(response, KernelResponse):
            return response.error_code
        if isinstance(response, dict):
            return str(response.get("error_code", ""))
        return ""

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

    def _notify_syscall_started(self, syscall: KernelSyscall) -> None:
        if self.agent_lifecycle is not None and getattr(syscall, "agent_id", ""):
            self.agent_lifecycle.on_syscall_started(syscall)

    def _notify_syscall_finished(self, syscall: KernelSyscall) -> None:
        if self.agent_lifecycle is not None and getattr(syscall, "agent_id", ""):
            self.agent_lifecycle.on_syscall_finished(syscall)
