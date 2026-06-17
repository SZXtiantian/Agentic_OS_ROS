from __future__ import annotations

from agentic_os.kernel.system_call.models import KernelSyscall

from .queues import KernelQueueStore


_GLOBAL_QUEUE_STORE = KernelQueueStore()


def get_global_queue_store() -> KernelQueueStore:
    return _GLOBAL_QUEUE_STORE


def reset_global_queue_store_for_tests() -> None:
    global _GLOBAL_QUEUE_STORE
    _GLOBAL_QUEUE_STORE = KernelQueueStore()


def global_queue_add_message(queue_name: str, syscall: KernelSyscall) -> None:
    _GLOBAL_QUEUE_STORE.add(queue_name, syscall)


def global_queue_get_message(queue_name: str, timeout_s: float | None = None) -> KernelSyscall | None:
    return _GLOBAL_QUEUE_STORE.get(queue_name, timeout_s=timeout_s)
