from __future__ import annotations

import threading
import time
from typing import Any

from agentic_os.kernel.hooks import KernelQueueStore
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
    ) -> None:
        self.queue_store = queue_store
        self.managers = managers
        self.lanes = lanes
        self.log_mode = log_mode
        self.poll_timeout_s = poll_timeout_s
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
            syscall = self.queue_store.get(lane.queue_name, timeout_s=self.poll_timeout_s)
            if syscall is None:
                continue
            self._execute_syscall(lane, syscall)

    def _execute_syscall(self, lane: SchedulerLaneSpec, syscall: KernelSyscall) -> None:
        manager_key = lane.manager_key or lane.queue_name
        manager = self.managers.get(manager_key) or self.managers.get(lane.queue_name)
        if manager is None:
            self._fail_syscall(syscall, "KERNEL_MANAGER_NOT_FOUND", f"manager not found for {manager_key}")
            return

        try:
            syscall.set_status(KernelSyscallStatus.EXECUTING)
            syscall.set_start_time(time.time())
            if hasattr(manager, "address_request"):
                response = manager.address_request(syscall)
            else:
                response = manager(syscall)
            syscall.set_response(response)
            if self._response_success(response):
                syscall.set_status(KernelSyscallStatus.DONE)
            else:
                syscall.error_code = self._response_error_code(response) or "KERNEL_MANAGER_REJECTED"
                syscall.set_status(KernelSyscallStatus.FAILED)
        except Exception as exc:
            self._fail_syscall(syscall, "KERNEL_MANAGER_FAILED", str(exc))
            return
        finally:
            syscall.set_end_time(time.time())
            syscall.ended_at = syscall.ended_at or utc_now()
            syscall.event.set()

    def _fail_syscall(self, syscall: KernelSyscall, error_code: str, reason: str) -> None:
        syscall.error_code = error_code
        syscall.set_response(KernelResponse(False, error_code=error_code, metadata={"reason": reason}))
        syscall.set_status(KernelSyscallStatus.FAILED)
        syscall.set_end_time(time.time())
        syscall.ended_at = syscall.ended_at or utc_now()
        syscall.event.set()

    def _response_success(self, response: Any) -> bool:
        if isinstance(response, KernelResponse):
            return response.success
        if isinstance(response, dict) and "success" in response:
            return bool(response["success"])
        return True

    def _response_error_code(self, response: Any) -> str:
        if isinstance(response, KernelResponse):
            return response.error_code
        if isinstance(response, dict):
            return str(response.get("error_code", ""))
        return ""
