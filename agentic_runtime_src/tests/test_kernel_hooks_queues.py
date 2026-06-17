from agentic_os.kernel.hooks import (
    KernelQueueName,
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
    store = KernelQueueStore()
    first = make_syscall("agent_a", 1)
    second = make_syscall("agent_a", 2)

    store.add(KernelQueueName.LLM, first)
    store.add(KernelQueueName.LLM, second)

    assert store.get(KernelQueueName.LLM, timeout_s=0.01) is first
    assert store.get(KernelQueueName.LLM, timeout_s=0.01) is second


def test_queue_get_timeout_returns_none():
    store = KernelQueueStore()

    assert store.get(KernelQueueName.MEMORY, timeout_s=0.01) is None


def test_queue_snapshot_counts_by_lane():
    store = KernelQueueStore()
    store.add(KernelQueueName.LLM, make_syscall("agent_a", 1))
    store.add(KernelQueueName.ROBOT_MOTION, make_syscall("agent_b", 2, KernelQueueName.ROBOT_MOTION))

    snapshot = store.snapshot()

    assert snapshot[KernelQueueName.LLM] == 1
    assert snapshot[KernelQueueName.ROBOT_MOTION] == 1
    assert snapshot[KernelQueueName.TOOL] == 0


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
