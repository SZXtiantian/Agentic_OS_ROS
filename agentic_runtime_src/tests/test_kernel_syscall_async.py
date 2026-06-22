from __future__ import annotations

from threading import Thread

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueName, KernelQueueStore
from agentic_os.kernel.system_call import (
    KernelResponse,
    KernelSyscall,
    KernelSyscallStatus,
    LLMQuery,
    MemoryQuery,
    SyscallExecutor,
)


def test_syscall_transition_helpers_and_agent_aliases():
    syscall = KernelSyscall.create("agent_a", "memory", "remember", {"key": "x"})
    syscall.aid = "aid-1"
    syscall.agent_id = "agent-id-1"

    syscall.mark_active()
    assert syscall.status == KernelSyscallStatus.ACTIVE
    syscall.mark_queued()
    assert syscall.status == KernelSyscallStatus.QUEUED
    syscall.mark_started()
    assert syscall.status == KernelSyscallStatus.EXECUTING
    syscall.mark_suspending()
    assert syscall.status == KernelSyscallStatus.SUSPENDING
    syscall.mark_suspended()
    assert syscall.status == KernelSyscallStatus.SUSPENDED
    syscall.mark_resuming()
    assert syscall.status == KernelSyscallStatus.RESUMING

    payload = syscall.to_dict()
    assert payload["aid"] == "aid-1"
    assert payload["agent_id"] == "agent-id-1"


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
    assert result.syscall.time_limit_s == 0.01


def test_executor_cancel_request_removes_only_queued_match():
    sink = InMemoryKernelEventSink()
    store = KernelQueueStore(event_sink=sink)
    executor = SyscallExecutor(queue_store=store, event_sink=sink)
    first = KernelSyscall.create("agent_a", KernelQueueName.MEMORY, "remember", {"memory_id": "first"})
    second = KernelSyscall.create("agent_a", KernelQueueName.MEMORY, "remember", {"memory_id": "second"})

    store.add(KernelQueueName.MEMORY, first)
    store.add(KernelQueueName.MEMORY, second)

    cancelled = executor.cancel_request(first.syscall_id)
    missing = executor.cancel_request("ksc_missing")

    assert cancelled.success is True
    assert cancelled.metadata["syscall_id"] == first.syscall_id
    assert first.status == KernelSyscallStatus.CANCELLED
    assert second.status == KernelSyscallStatus.QUEUED
    assert store.drain(KernelQueueName.MEMORY) == [second]
    assert missing.success is False
    assert missing.error_code == "SYSCALL_NOT_FOUND"
    assert any(
        event["event_type"] == "syscall.cancelled" and event["metadata"]["syscall_id"] == first.syscall_id
        for event in sink.recent(limit=10)
    )


def test_cancel_reject_and_response_helpers_set_event():
    cancelled = KernelSyscall.create("agent_a", "memory", "recall")
    cancelled.cancel("user requested")

    assert cancelled.status == KernelSyscallStatus.CANCELLED
    assert cancelled.error_code == "KERNEL_SYSCALL_CANCELLED"
    assert cancelled.wait(timeout_s=0.01) is True

    rejected = KernelSyscall.create("agent_a", "missing", "noop")
    rejected.reject("KERNEL_SYSCALL_TARGET_NOT_FOUND", "missing manager")

    assert rejected.status == KernelSyscallStatus.REJECTED
    assert rejected.response["error_code"] == "KERNEL_SYSCALL_TARGET_NOT_FOUND"
    assert rejected.wait(timeout_s=0.01) is True

    ok = KernelResponse.ok({"value": 1}, metadata={"queue": "memory"})
    err = KernelResponse.error("NOPE", metadata={"reason": "test"})

    assert ok.success is True
    assert ok.response_message == {"value": 1}
    assert ok.metadata["queue"] == "memory"
    assert err.success is False
    assert err.error_code == "NOPE"


def test_execute_missing_target_rejects_with_structured_error():
    executor = SyscallExecutor()
    syscall = KernelSyscall.create("agent_a", "missing", "noop")

    result = executor.execute(syscall)

    assert result.success is False
    assert result.error_code == "KERNEL_SYSCALL_TARGET_NOT_FOUND"
    assert syscall.status == KernelSyscallStatus.REJECTED
    assert syscall.wait(timeout_s=0.01) is True
