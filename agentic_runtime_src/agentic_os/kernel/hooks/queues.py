from __future__ import annotations

from queue import Empty, Queue
from threading import Lock

from agentic_os.kernel.system_call.models import KernelSyscall

from .types import DEFAULT_KERNEL_QUEUES


class KernelQueueStore:
    """Thread-safe named FIFO queues for kernel module syscalls."""

    def __init__(self, queue_names: tuple[str, ...] = DEFAULT_KERNEL_QUEUES) -> None:
        self._lock = Lock()
        self._queues: dict[str, Queue[KernelSyscall]] = {name: Queue() for name in queue_names}

    def add(self, queue_name: str, syscall: KernelSyscall) -> None:
        self._queue(queue_name).put(syscall)

    def get(self, queue_name: str, timeout_s: float | None = None) -> KernelSyscall | None:
        try:
            return self._queue(queue_name).get(timeout=timeout_s)
        except Empty:
            return None

    def qsize(self, queue_name: str) -> int:
        return self._queue(queue_name).qsize()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {name: queue.qsize() for name, queue in sorted(self._queues.items())}

    def clear(self) -> None:
        with self._lock:
            self._queues = {name: Queue() for name in self._queues}

    def _queue(self, queue_name: str) -> Queue[KernelSyscall]:
        with self._lock:
            if queue_name not in self._queues:
                self._queues[queue_name] = Queue()
            return self._queues[queue_name]
