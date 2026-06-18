from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Condition, Lock

from agentic_os.kernel.system_call.models import KernelSyscall

from .events import KernelEventSink
from .types import DEFAULT_KERNEL_QUEUES, KernelQueueName


@dataclass(frozen=True)
class KernelQueuePolicy:
    max_size: int | None = None
    on_full: str = "reject"


@dataclass
class _QueueStats:
    added_count: int = 0
    got_count: int = 0
    rejected_count: int = 0
    timeout_count: int = 0
    total_wait_ms: float = 0.0
    backpressure_count: int = 0


@dataclass
class _QueuedSyscall:
    syscall: KernelSyscall
    enqueued_at: float


class KernelQueueStore:
    """Thread-safe centralized queues for kernel module syscalls."""

    def __init__(
        self,
        queue_names: tuple[str, ...] = DEFAULT_KERNEL_QUEUES,
        policies: dict[str, KernelQueuePolicy] | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self._condition = Condition(Lock())
        self._queues: dict[str, deque[_QueuedSyscall]] = {name: deque() for name in queue_names}
        self._stats: dict[str, _QueueStats] = {name: _QueueStats() for name in queue_names}
        self._policies = dict(_default_policies())
        self.event_sink = event_sink
        if policies:
            self._policies.update(policies)

    def add(self, queue_name: str, syscall: KernelSyscall, timeout_s: float | None = None) -> bool:
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        with self._condition:
            queue = self._queue_unlocked(queue_name)
            policy = self._policy(queue_name)
            emergency = self._is_emergency_stop(syscall)
            while self._is_full(queue_name) and not emergency:
                if policy.on_full == "drop_oldest":
                    dropped = queue.popleft().syscall
                    dropped.reject("KERNEL_QUEUE_DROPPED_OLDEST", f"queue {queue_name} dropped oldest syscall")
                    break
                if policy.on_full == "block":
                    remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                    if remaining == 0.0 or not self._condition.wait(timeout=remaining):
                        self._reject_full(queue_name, syscall)
                        return False
                    continue
                self._reject_full(queue_name, syscall)
                return False

            syscall.mark_queued()
            item = _QueuedSyscall(syscall=syscall, enqueued_at=time.monotonic())
            if emergency:
                queue.appendleft(item)
            else:
                queue.append(item)
            self._stats[queue_name].added_count += 1
            self._condition.notify_all()
            self._emit("queue.added", queue_name=queue_name, syscall_id=syscall.syscall_id, agent_name=syscall.agent_name)
            return True

    def get(self, queue_name: str, timeout_s: float | None = None) -> KernelSyscall | None:
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        with self._condition:
            while not self._queue_unlocked(queue_name):
                if timeout_s is None:
                    self._condition.wait()
                    continue
                remaining = max(0.0, deadline - time.monotonic()) if deadline is not None else 0.0
                if remaining == 0.0 or not self._condition.wait(timeout=remaining):
                    self._stats[queue_name].timeout_count += 1
                    return None
            item = self._queue_unlocked(queue_name).popleft()
            stats = self._stats[queue_name]
            stats.got_count += 1
            stats.total_wait_ms += (time.monotonic() - item.enqueued_at) * 1000.0
            self._condition.notify_all()
            self._emit("queue.dequeued", queue_name=queue_name, syscall_id=item.syscall.syscall_id, agent_name=item.syscall.agent_name)
            return item.syscall

    def peek(self, queue_name: str) -> KernelSyscall | None:
        with self._condition:
            queue = self._queue_unlocked(queue_name)
            return queue[0].syscall if queue else None

    def size(self, queue_name: str) -> int:
        return self.qsize(queue_name)

    def qsize(self, queue_name: str) -> int:
        with self._condition:
            return len(self._queue_unlocked(queue_name))

    def snapshot(self) -> dict[str, dict[str, int | float]]:
        now = time.monotonic()
        with self._condition:
            result: dict[str, dict[str, int | float]] = {}
            for name in sorted(self._queues):
                queue = self._queue_unlocked(name)
                stats = self._stats[name]
                oldest_age_ms = int((now - queue[0].enqueued_at) * 1000) if queue else 0
                avg_wait_ms = stats.total_wait_ms / stats.got_count if stats.got_count else 0.0
                result[name] = {
                    "size": len(queue),
                    "oldest_age_ms": oldest_age_ms,
                    "added_count": stats.added_count,
                    "got_count": stats.got_count,
                    "rejected_count": stats.rejected_count,
                    "timeout_count": stats.timeout_count,
                    "avg_wait_ms": avg_wait_ms,
                    "backpressure_count": stats.backpressure_count,
                }
            return result

    def drain(self, queue_name: str) -> list[KernelSyscall]:
        with self._condition:
            queue = self._queue_unlocked(queue_name)
            drained = [item.syscall for item in queue]
            queue.clear()
            self._condition.notify_all()
            return drained

    def remove(self, syscall_id: str) -> KernelSyscall | None:
        with self._condition:
            for queue in self._queues.values():
                for item in list(queue):
                    if item.syscall.syscall_id == syscall_id:
                        queue.remove(item)
                        item.syscall.cancel("removed from queue before execution")
                    self._condition.notify_all()
                    self._emit("syscall.cancelled", queue_name="unknown", syscall_id=item.syscall.syscall_id, agent_name=item.syscall.agent_name)
                    return item.syscall
            return None

    def mark_backpressure(self, queue_name: str) -> None:
        with self._condition:
            self._queue_unlocked(queue_name)
            self._stats[queue_name].backpressure_count += 1
            self._stats[queue_name].rejected_count += 1

    def clear(self) -> None:
        with self._condition:
            self._queues = {name: deque() for name in self._queues}
            self._stats = {name: _QueueStats() for name in self._queues}
            self._condition.notify_all()

    def _reject_full(self, queue_name: str, syscall: KernelSyscall) -> None:
        stats = self._stats[queue_name]
        stats.rejected_count += 1
        stats.backpressure_count += 1
        syscall.reject("KERNEL_QUEUE_FULL", f"queue {queue_name} is full")
        self._emit("queue.rejected", queue_name=queue_name, syscall_id=syscall.syscall_id, agent_name=syscall.agent_name, error_code="KERNEL_QUEUE_FULL")

    def _queue_unlocked(self, queue_name: str) -> deque[_QueuedSyscall]:
        if queue_name not in self._queues:
            self._queues[queue_name] = deque()
            self._stats[queue_name] = _QueueStats()
        return self._queues[queue_name]

    def _policy(self, queue_name: str) -> KernelQueuePolicy:
        return self._policies.get(queue_name, KernelQueuePolicy())

    def _is_full(self, queue_name: str) -> bool:
        policy = self._policy(queue_name)
        return policy.max_size is not None and len(self._queue_unlocked(queue_name)) >= policy.max_size

    def _is_emergency_stop(self, syscall: KernelSyscall) -> bool:
        skill_name = str(getattr(getattr(syscall, "query", None), "skill_name", "") or syscall.params.get("skill_name", ""))
        operation = str(syscall.operation_type or "")
        return operation in {"stop", "emergency_stop"} or skill_name in {"robot.stop", "emergency_stop"}

    def _emit(self, event_type: str, **metadata) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(event_type, **metadata)


def _default_policies() -> dict[str, KernelQueuePolicy]:
    return {
        KernelQueueName.LLM: KernelQueuePolicy(max_size=None, on_full="block"),
        KernelQueueName.MEMORY: KernelQueuePolicy(max_size=None, on_full="reject"),
        KernelQueueName.STORAGE: KernelQueuePolicy(max_size=None, on_full="reject"),
        KernelQueueName.TOOL: KernelQueuePolicy(max_size=None, on_full="reject"),
        KernelQueueName.ROBOT_MOTION: KernelQueuePolicy(max_size=None, on_full="reject"),
        KernelQueueName.ROBOT_SENSOR: KernelQueuePolicy(max_size=None, on_full="block"),
        KernelQueueName.HUMAN: KernelQueuePolicy(max_size=None, on_full="block"),
    }
