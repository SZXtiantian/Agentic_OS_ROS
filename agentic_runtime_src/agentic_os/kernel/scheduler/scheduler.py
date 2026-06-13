from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Deque, Iterable

from agentic_os.kernel.system_call import KernelSyscall, SyscallExecutionResult, SyscallExecutor


@dataclass
class SchedulerStatus:
    policy: str
    queued: int
    active: bool = False

    def to_dict(self) -> dict[str, object]:
        return {"policy": self.policy, "queued": self.queued, "active": self.active}


class FIFORequestScheduler:
    """FIFO syscall scheduler adapted from AIOS for single-robot safety.

    AIOS has independent queues for LLM/memory/storage/tool. For embodied
    robotics, this FIFO scheduler serializes kernel syscalls so high-level
    robot capabilities pass through permission, arbitration, and audit in a
    predictable order.
    """

    def __init__(self, executor: SyscallExecutor | None = None) -> None:
        self.executor = executor or SyscallExecutor()
        self._queue: Deque[KernelSyscall] = deque()
        self._lock = Lock()
        self._active = False

    def submit(self, syscall: KernelSyscall) -> str:
        syscall.mark_queued()
        with self._lock:
            self._queue.append(syscall)
        return syscall.syscall_id

    def run_next(self) -> SyscallExecutionResult | None:
        with self._lock:
            if not self._queue:
                return None
            syscall = self._queue.popleft()
            self._active = True
        try:
            return self.executor.execute(syscall)
        finally:
            with self._lock:
                self._active = False

    def drain(self) -> list[SyscallExecutionResult]:
        results: list[SyscallExecutionResult] = []
        while True:
            result = self.run_next()
            if result is None:
                return results
            results.append(result)

    def status(self) -> dict[str, object]:
        with self._lock:
            return SchedulerStatus("fifo", len(self._queue), self._active).to_dict()


class RoundRobinRequestScheduler:
    """Fair scheduler for non-realtime agent syscalls.

    This ports AIOS's round-robin scheduling idea while keeping robot control
    out of realtime loops. It is intended for LLM, memory, storage, and generic
    tool work, not low-level actuation.
    """

    def __init__(self, executor: SyscallExecutor | None = None) -> None:
        self.executor = executor or SyscallExecutor()
        self._queues: dict[str, Deque[KernelSyscall]] = defaultdict(deque)
        self._agents: Deque[str] = deque()
        self._lock = Lock()

    def submit(self, syscall: KernelSyscall) -> str:
        syscall.mark_queued()
        with self._lock:
            if syscall.agent_name not in self._queues:
                self._agents.append(syscall.agent_name)
            self._queues[syscall.agent_name].append(syscall)
        return syscall.syscall_id

    def run_next(self) -> SyscallExecutionResult | None:
        with self._lock:
            while self._agents:
                agent = self._agents.popleft()
                queue = self._queues.get(agent)
                if not queue:
                    self._queues.pop(agent, None)
                    continue
                syscall = queue.popleft()
                if queue:
                    self._agents.append(agent)
                else:
                    self._queues.pop(agent, None)
                break
            else:
                return None
        return self.executor.execute(syscall)

    def drain(self) -> list[SyscallExecutionResult]:
        results: list[SyscallExecutionResult] = []
        while True:
            result = self.run_next()
            if result is None:
                return results
            results.append(result)

    def status(self) -> dict[str, object]:
        with self._lock:
            queued = sum(len(queue) for queue in self._queues.values())
        return SchedulerStatus("round_robin", queued, active=False).to_dict()

