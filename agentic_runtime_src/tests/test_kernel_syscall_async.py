from __future__ import annotations

from threading import Thread

from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore
from agentic_os.kernel.system_call import (
    KernelResponse,
    KernelSyscall,
    KernelSyscallStatus,
    LLMQuery,
    MemoryQuery,
    SyscallExecutor,
)


def test_syscall_has_event_and_wait():
    syscall = KernelSyscall.create("agent_a", "memory", "remember", {"key": "x"})

    assert syscall.wait(timeout_s=0.01) is False

    syscall.finish(response={"success": True})

    assert syscall.wait(timeout_s=0.01) is True
    assert syscall.status == KernelSyscallStatus.DONE


def test_executor_legacy_register_execute_still_works():
    executor = SyscallExecutor()
    executor.register("echo", lambda syscall: {"value": syscall.params["value"]})
    syscall = KernelSyscall.create("agent_a", "echo", "echo", {"value": 42})

    result = executor.execute(syscall)

    assert result.success is True
    assert result.response == {"value": 42}
    assert syscall.status == KernelSyscallStatus.DONE


def test_execute_request_queues_syscall_and_waits_for_scheduler():
    store = KernelQueueStore()
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    def fake_scheduler() -> None:
        syscall = store.get(KernelQueueName.LLM, timeout_s=1.0)
        assert syscall is not None
        syscall.mark_started()
        response = KernelResponse(True, response_message={"text": "hello"})
        syscall.finish(response=response, status=KernelSyscallStatus.DONE)

    worker = Thread(target=fake_scheduler)
    worker.start()
    result = executor.execute_request(
        "agent_a",
        LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hi"}]),
        timeout_s=1.0,
    )
    worker.join(timeout=1.0)

    assert result.success is True
    assert result.metadata["queue_name"] == KernelQueueName.LLM
    assert result.metadata["pid"] == 1
    assert isinstance(result.response, KernelResponse)
    assert result.response.response_message == {"text": "hello"}
    assert result.syscall.status == KernelSyscallStatus.DONE


def test_execute_request_timeout_sets_timeout_status():
    store = KernelQueueStore()
    executor = SyscallExecutor(queue_store=store)

    result = executor.execute_request("agent_a", MemoryQuery(operation_type="recall"), timeout_s=0.01)

    assert result.success is False
    assert result.error_code == "KERNEL_SYSCALL_TIMEOUT"
    assert result.syscall.status == KernelSyscallStatus.TIMEOUT
    assert result.syscall.wait(timeout_s=0.01) is True
