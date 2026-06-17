from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore
from agentic_os.kernel.scheduler import FIFOKernelScheduler, SchedulerLaneSpec
from agentic_os.kernel.system_call import (
    KernelResponse,
    KernelSyscallStatus,
    LLMQuery,
    MemoryQuery,
    SyscallExecutor,
)


class FakeManager:
    def __init__(self, response=None, fail: bool = False) -> None:
        self.response = response if response is not None else {"success": True, "value": "ok"}
        self.fail = fail
        self.calls = []

    def address_request(self, syscall):
        self.calls.append(syscall)
        if self.fail:
            raise RuntimeError("boom")
        return self.response


def test_scheduler_starts_and_stops_processing_threads():
    store = KernelQueueStore()
    scheduler = FIFOKernelScheduler(store, managers={})

    scheduler.start()
    status = scheduler.status()

    assert status["active"] is True
    assert status["threads"]
    assert all(status["threads"].values())

    scheduler.stop()

    assert scheduler.status()["active"] is False
    assert scheduler.status()["threads"] == {}


def test_scheduler_executes_llm_syscall_from_queue():
    store = KernelQueueStore()
    manager = FakeManager(KernelResponse(True, response_message={"text": "ok"}))
    scheduler = FIFOKernelScheduler(store, managers={"llm": manager})
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    scheduler.start()
    try:
        result = executor.execute_request("agent_a", LLMQuery(operation_type="chat"), timeout_s=1.0)
    finally:
        scheduler.stop()

    assert result.success is True
    assert manager.calls
    assert result.syscall.status == KernelSyscallStatus.DONE


def test_scheduler_sets_event_on_success():
    store = KernelQueueStore()
    manager = FakeManager({"success": True, "value": 1})
    scheduler = FIFOKernelScheduler(store, managers={"memory": manager})
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    scheduler.start()
    try:
        result = executor.execute_request("agent_a", MemoryQuery(operation_type="remember"), timeout_s=1.0)
    finally:
        scheduler.stop()

    assert result.syscall.wait(timeout_s=0.01) is True
    assert result.syscall.status == KernelSyscallStatus.DONE


def test_scheduler_sets_event_on_failure():
    store = KernelQueueStore()
    manager = FakeManager(fail=True)
    scheduler = FIFOKernelScheduler(store, managers={"memory": manager})
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    scheduler.start()
    try:
        result = executor.execute_request("agent_a", MemoryQuery(operation_type="remember"), timeout_s=1.0)
    finally:
        scheduler.stop()

    assert result.success is False
    assert result.syscall.wait(timeout_s=0.01) is True
    assert result.syscall.status == KernelSyscallStatus.FAILED
    assert result.error_code == "KERNEL_MANAGER_FAILED"


def test_scheduler_status_reports_queue_sizes():
    store = KernelQueueStore()
    store.add(KernelQueueName.MEMORY, SyscallExecutor(queue_store=store).create_syscall("agent_a", "memory", "noop"))
    scheduler = FIFOKernelScheduler(store, managers={})

    status = scheduler.status()

    assert status["queues"][KernelQueueName.MEMORY] == 1


def test_scheduler_accepts_custom_lane_specs():
    store = KernelQueueStore()
    lane = SchedulerLaneSpec("memory", KernelQueueName.MEMORY, concurrent=True, manager_key="memory")
    scheduler = FIFOKernelScheduler(store, managers={"memory": FakeManager()}, lanes=(lane,))

    scheduler.start()
    scheduler.stop()

    assert scheduler.status()["lanes"] == ["memory"]
