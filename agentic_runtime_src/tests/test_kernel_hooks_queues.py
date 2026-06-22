from agentic_os.kernel.hooks import (
    InMemoryKernelEventSink,
    KernelQueueName,
    KernelQueuePolicy,
    KernelQueueStore,
    get_global_queue_store,
    global_queue_add_message,
    global_queue_get_message,
    reset_global_queue_store_for_tests,
)
from agentic_os.kernel.system_call import KernelSyscall


def make_syscall(agent_name: str, value: int, target: str = KernelQueueName.LLM) -> KernelSyscall:
    return KernelSyscall.create(agent_name, target, "echo", {"value": value})


def test_queue_add_get_fifo_order():
    sink = InMemoryKernelEventSink()
    store = KernelQueueStore(event_sink=sink)
    first = make_syscall("agent_a", 1)
    second = make_syscall("agent_a", 2)

    store.add(KernelQueueName.LLM, first)
    store.add(KernelQueueName.LLM, second)

    assert store.get(KernelQueueName.LLM, timeout_s=0.01) is first
    assert store.get(KernelQueueName.LLM, timeout_s=0.01) is second
    assert [event["event_type"] for event in sink.recent()] == [
        "queue.added",
        "queue.added",
        "queue.dequeued",
        "queue.dequeued",
    ]


def test_queue_get_timeout_returns_none():
    store = KernelQueueStore()

    assert store.get(KernelQueueName.MEMORY, timeout_s=0.01) is None


def test_queue_snapshot_counts_by_lane():
    store = KernelQueueStore()
    store.add(KernelQueueName.LLM, make_syscall("agent_a", 1))
    store.add(KernelQueueName.ROBOT_MOTION, make_syscall("agent_b", 2, KernelQueueName.ROBOT_MOTION))

    snapshot = store.snapshot()

    assert snapshot[KernelQueueName.LLM]["size"] == 1
    assert snapshot[KernelQueueName.LLM]["added_count"] == 1
    assert snapshot[KernelQueueName.ROBOT_MOTION]["size"] == 1
    assert snapshot[KernelQueueName.TOOL]["size"] == 0
    assert "avg_wait_ms" in snapshot[KernelQueueName.LLM]


def test_global_queue_reset_for_tests():
    reset_global_queue_store_for_tests()
    syscall = make_syscall("agent_a", 1)
    global_queue_add_message(KernelQueueName.STORAGE, syscall)

    assert get_global_queue_store().qsize(KernelQueueName.STORAGE) == 1

    reset_global_queue_store_for_tests()
    assert global_queue_get_message(KernelQueueName.STORAGE, timeout_s=0.01) is None


def test_robot_motion_queue_is_distinct_from_tool_queue():
    store = KernelQueueStore()
    motion = make_syscall("agent_a", 1, KernelQueueName.ROBOT_MOTION)
    tool = make_syscall("agent_a", 2, KernelQueueName.TOOL)

    store.add(KernelQueueName.ROBOT_MOTION, motion)
    store.add(KernelQueueName.TOOL, tool)

    assert store.get(KernelQueueName.TOOL, timeout_s=0.01) is tool
    assert store.get(KernelQueueName.ROBOT_MOTION, timeout_s=0.01) is motion


def test_queue_peek_drain_and_remove_cancel_unexecuted_syscall():
    store = KernelQueueStore()
    first = make_syscall("agent_a", 1, KernelQueueName.MEMORY)
    second = make_syscall("agent_a", 2, KernelQueueName.MEMORY)

    store.add(KernelQueueName.MEMORY, first)
    store.add(KernelQueueName.MEMORY, second)

    assert store.peek(KernelQueueName.MEMORY) is first
    removed = store.remove(first.syscall_id)
    assert removed is first
    assert removed.status == "cancelled"
    assert store.peek(KernelQueueName.MEMORY) is second
    assert store.drain(KernelQueueName.MEMORY) == [second]
    assert store.size(KernelQueueName.MEMORY) == 0


def test_queue_remove_missing_syscall_is_precise_noop():
    sink = InMemoryKernelEventSink()
    store = KernelQueueStore(event_sink=sink)
    first = make_syscall("agent_a", 1, KernelQueueName.MEMORY)
    second = make_syscall("agent_a", 2, KernelQueueName.MEMORY)

    store.add(KernelQueueName.MEMORY, first)
    store.add(KernelQueueName.MEMORY, second)

    assert store.remove("ksc_missing") is None
    assert store.size(KernelQueueName.MEMORY) == 2
    assert first.status == "queued"
    assert second.status == "queued"
    assert [event["event_type"] for event in sink.recent()] == ["queue.added", "queue.added"]


def test_queue_remove_cancels_only_matching_middle_syscall():
    store = KernelQueueStore()
    first = make_syscall("agent_a", 1, KernelQueueName.MEMORY)
    second = make_syscall("agent_a", 2, KernelQueueName.MEMORY)
    third = make_syscall("agent_a", 3, KernelQueueName.MEMORY)

    store.add(KernelQueueName.MEMORY, first)
    store.add(KernelQueueName.MEMORY, second)
    store.add(KernelQueueName.MEMORY, third)

    removed = store.remove(second.syscall_id)

    assert removed is second
    assert second.status == "cancelled"
    assert first.status == "queued"
    assert third.status == "queued"
    assert store.drain(KernelQueueName.MEMORY) == [first, third]


def test_full_queue_reject_policy_is_deterministic():
    store = KernelQueueStore(
        policies={KernelQueueName.MEMORY: KernelQueuePolicy(max_size=1, on_full="reject")}
    )
    first = make_syscall("agent_a", 1, KernelQueueName.MEMORY)
    second = make_syscall("agent_a", 2, KernelQueueName.MEMORY)

    assert store.add(KernelQueueName.MEMORY, first) is True
    assert store.add(KernelQueueName.MEMORY, second) is False

    snapshot = store.snapshot()[KernelQueueName.MEMORY]
    assert snapshot["size"] == 1
    assert snapshot["rejected_count"] == 1
    assert second.status == "rejected"
    assert second.error_code == "KERNEL_QUEUE_FULL"


def test_emergency_stop_gets_priority_over_robot_motion_backlog():
    store = KernelQueueStore(
        policies={KernelQueueName.ROBOT_MOTION: KernelQueuePolicy(max_size=1, on_full="reject")}
    )
    navigate = make_syscall("agent_a", 1, KernelQueueName.ROBOT_MOTION)
    stop = KernelSyscall.create("agent_b", KernelQueueName.ROBOT_MOTION, "stop", {"skill_name": "robot.stop"})

    assert store.add(KernelQueueName.ROBOT_MOTION, navigate) is True
    assert store.add(KernelQueueName.ROBOT_MOTION, stop) is True

    assert store.get(KernelQueueName.ROBOT_MOTION, timeout_s=0.01) is stop
    assert store.get(KernelQueueName.ROBOT_MOTION, timeout_s=0.01) is navigate
