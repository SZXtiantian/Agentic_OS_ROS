from __future__ import annotations

import threading

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueName, KernelQueueStore
from agentic_os.kernel.llm_core import LLMAdapter, LLMConfig
from agentic_os.kernel.scheduler import BaseKernelScheduler, FIFOKernelScheduler, SchedulerLaneSpec
from agentic_os.kernel.system_call import (
    KernelResponse,
    KernelSyscall,
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


class TimeoutManager:
    def address_request(self, syscall):
        raise TimeoutError("manager timed out")


class BatchProvider:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def complete(self, query):
        return KernelResponse.ok({"fallback": True})

    def complete_batch(self, queries):
        self.batch_sizes.append(len(queries))
        return [KernelResponse.ok({"index": index}) for index, _query in enumerate(queries)]


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


def test_scheduler_converts_manager_timeout_to_structured_error():
    store = KernelQueueStore()
    scheduler = FIFOKernelScheduler(store, managers={"memory": TimeoutManager()})
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    scheduler.start()
    try:
        result = executor.execute_request("agent_a", MemoryQuery(operation_type="remember"), timeout_s=1.0)
    finally:
        scheduler.stop()

    assert result.success is False
    assert result.syscall.status == KernelSyscallStatus.FAILED
    assert result.error_code == "KERNEL_MANAGER_TIMEOUT"


def test_scheduler_batches_llm_syscalls_in_window():
    store = KernelQueueStore()
    provider = BatchProvider()
    manager = LLMAdapter([LLMConfig(name="batch", backend="openai_compatible")], providers={"batch": provider})
    lane = SchedulerLaneSpec(
        "llm",
        KernelQueueName.LLM,
        concurrent=True,
        manager_key="llm",
        batchable=True,
        batch_window_ms=40,
        max_batch_size=8,
    )
    scheduler = FIFOKernelScheduler(store, managers={"llm": manager}, lanes=(lane,), poll_timeout_s=0.01)
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)
    results = []

    scheduler.start()
    try:
        threads = [
            threading.Thread(
                target=lambda i=index: results.append(
                    executor.execute_request("agent_a", LLMQuery(operation_type="chat", params={"i": i}), timeout_s=1.0)
                )
            )
            for index in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1.0)
    finally:
        scheduler.stop()

    assert provider.batch_sizes == [3]
    assert len(results) == 3
    assert all(result.success for result in results)
    assert sorted(result.response.response_message["index"] for result in results) == [0, 1, 2]


def test_scheduler_releases_batch_syscall_after_manager_done_event():
    store = KernelQueueStore()
    sink = InMemoryKernelEventSink()
    provider = BatchProvider()
    manager = LLMAdapter([LLMConfig(name="batch", backend="openai_compatible")], providers={"batch": provider})
    lane = SchedulerLaneSpec(
        "llm",
        KernelQueueName.LLM,
        concurrent=True,
        manager_key="llm",
        batchable=True,
        batch_window_ms=10,
        max_batch_size=8,
    )
    scheduler = FIFOKernelScheduler(store, managers={"llm": manager}, lanes=(lane,), poll_timeout_s=0.01, event_sink=sink)
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0, event_sink=sink)

    scheduler.start()
    try:
        result = executor.execute_request("agent_a", LLMQuery(operation_type="chat"), timeout_s=1.0)
        event_types = [event["event_type"] for event in sink.recent(limit=20)]
    finally:
        scheduler.stop()

    assert result.success is True
    assert result.syscall.status == KernelSyscallStatus.DONE
    assert "manager.done" in event_types
    assert event_types.index("syscall.done") < event_types.index("manager.done")


def test_scheduler_status_reports_queue_sizes():
    store = KernelQueueStore()
    store.add(KernelQueueName.MEMORY, SyscallExecutor(queue_store=store).create_syscall("agent_a", "memory", "noop"))
    scheduler = FIFOKernelScheduler(store, managers={})

    status = scheduler.status()

    assert status["queues"][KernelQueueName.MEMORY]["size"] == 1


def test_scheduler_accepts_custom_lane_specs():
    store = KernelQueueStore()
    lane = SchedulerLaneSpec("memory", KernelQueueName.MEMORY, concurrent=True, manager_key="memory")
    scheduler = FIFOKernelScheduler(store, managers={"memory": FakeManager()}, lanes=(lane,))

    scheduler.start()
    scheduler.stop()

    assert scheduler.status()["lanes"] == ["memory"]


def test_scheduler_repeated_start_stop_does_not_leak_threads():
    scheduler = FIFOKernelScheduler(KernelQueueStore(), managers={})

    scheduler.start()
    first_threads = set(scheduler.status()["threads"])
    scheduler.start()
    assert set(scheduler.status()["threads"]) == first_threads
    scheduler.stop()
    scheduler.stop()

    assert scheduler.status()["threads"] == {}


def test_scheduler_skips_cancelled_syscall_without_manager_call():
    manager = FakeManager()
    scheduler = BaseKernelScheduler(KernelQueueStore(), managers={"memory": manager})
    lane = SchedulerLaneSpec("memory", KernelQueueName.MEMORY, concurrent=True, manager_key="memory")
    syscall = KernelSyscall.create("agent_a", "memory", "remember")
    syscall.cancel("operator")

    scheduler._execute_syscall(lane, syscall)

    assert syscall.status == KernelSyscallStatus.CANCELLED
    assert syscall.wait(timeout_s=0.01) is True
    assert manager.calls == []


def test_scheduler_times_out_expired_syscall_before_manager_call():
    manager = FakeManager()
    scheduler = BaseKernelScheduler(KernelQueueStore(), managers={"memory": manager})
    lane = SchedulerLaneSpec("memory", KernelQueueName.MEMORY, concurrent=True, manager_key="memory")
    syscall = KernelSyscall.create("agent_a", "memory", "remember")
    syscall.time_limit_s = 0.0

    scheduler._execute_syscall(lane, syscall)

    assert syscall.status == KernelSyscallStatus.TIMEOUT
    assert syscall.error_code == "KERNEL_SYSCALL_TIMEOUT"
    assert syscall.wait(timeout_s=0.01) is True
    assert manager.calls == []
