from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore
from agentic_os.kernel.system_call import KernelSyscall, KernelSyscallStatus, SyscallExecutor


def _syscall(syscall_id: str, target: str = "memory", operation_type: str = "remember") -> KernelSyscall:
    syscall = KernelSyscall.create("agent_a", target, operation_type)
    syscall.syscall_id = syscall_id
    return syscall


def test_queue_remove_missing_id_preserves_all_queued_syscalls():
    store = KernelQueueStore()
    first = _syscall("ksc_first")
    second = _syscall("ksc_second")
    third = _syscall("ksc_third")
    for syscall in (first, second, third):
        assert store.add(KernelQueueName.MEMORY, syscall) is True

    removed = store.remove("ksc_missing")

    assert removed is None
    assert store.qsize(KernelQueueName.MEMORY) == 3
    assert [syscall.syscall_id for syscall in store.drain(KernelQueueName.MEMORY)] == [
        "ksc_first",
        "ksc_second",
        "ksc_third",
    ]
    assert [first.status, second.status, third.status] == [
        KernelSyscallStatus.QUEUED,
        KernelSyscallStatus.QUEUED,
        KernelSyscallStatus.QUEUED,
    ]


def test_queue_remove_cancels_only_exact_middle_match_and_preserves_order():
    store = KernelQueueStore()
    first = _syscall("ksc_first")
    second = _syscall("ksc_second")
    third = _syscall("ksc_third")
    for syscall in (first, second, third):
        assert store.add(KernelQueueName.MEMORY, syscall) is True

    removed = store.remove("ksc_second")

    assert removed is second
    assert second.status == KernelSyscallStatus.CANCELLED
    assert second.error_code == "KERNEL_SYSCALL_CANCELLED"
    assert second.wait(timeout_s=0.01) is True
    assert [syscall.syscall_id for syscall in store.drain(KernelQueueName.MEMORY)] == ["ksc_first", "ksc_third"]
    assert first.status == KernelSyscallStatus.QUEUED
    assert third.status == KernelSyscallStatus.QUEUED


def test_queue_remove_searches_all_queues_without_mutating_non_matches():
    store = KernelQueueStore()
    memory = _syscall("ksc_memory", target="memory")
    llm = _syscall("ksc_llm", target="llm", operation_type="chat")
    assert store.add(KernelQueueName.MEMORY, memory) is True
    assert store.add(KernelQueueName.LLM, llm) is True

    removed = store.remove("ksc_llm")

    assert removed is llm
    assert llm.status == KernelSyscallStatus.CANCELLED
    assert store.qsize(KernelQueueName.LLM) == 0
    assert store.qsize(KernelQueueName.MEMORY) == 1
    assert store.peek(KernelQueueName.MEMORY) is memory
    assert memory.status == KernelSyscallStatus.QUEUED


def test_executor_cancel_missing_syscall_returns_not_found_without_queue_side_effects():
    store = KernelQueueStore()
    executor = SyscallExecutor(queue_store=store)
    queued = _syscall("ksc_keep")
    assert store.add(KernelQueueName.MEMORY, queued) is True

    response = executor.cancel_request("ksc_missing")

    assert response.success is False
    assert response.error_code == "SYSCALL_NOT_FOUND"
    assert response.metadata["syscall_id"] == "ksc_missing"
    assert store.qsize(KernelQueueName.MEMORY) == 1
    assert store.peek(KernelQueueName.MEMORY) is queued
    assert queued.status == KernelSyscallStatus.QUEUED


def test_executor_cancel_exact_queued_syscall_reports_cancelled_metadata():
    store = KernelQueueStore()
    executor = SyscallExecutor(queue_store=store)
    queued = _syscall("ksc_cancel_me")
    queued.set_pid(7)
    assert store.add(KernelQueueName.MEMORY, queued) is True

    response = executor.cancel_request("ksc_cancel_me")

    assert response.success is True
    assert response.data == {"cancelled": ["ksc_cancel_me"]}
    assert response.metadata["syscall_id"] == "ksc_cancel_me"
    assert response.metadata["queue_name"] == "memory"
    assert response.metadata["pid"] == 7
    assert response.metadata["status"] == KernelSyscallStatus.CANCELLED
    assert queued.status == KernelSyscallStatus.CANCELLED
    assert store.qsize(KernelQueueName.MEMORY) == 0
