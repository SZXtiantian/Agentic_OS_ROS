from agentic_os.kernel.agent import AgentCleanupManager, AgentLifecycleManager, AgentResourceRegistry, AgentStatus, AgentTable
from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore
from agentic_os.kernel.system_call import KernelSyscall, KernelSyscallStatus


def _syscall(agent_id: str, value: str) -> KernelSyscall:
    syscall = KernelSyscall.create("app_a", KernelQueueName.MEMORY, "remember", {"value": value})
    syscall.agent_id = agent_id
    syscall.aid = agent_id
    syscall.queue_name = KernelQueueName.MEMORY
    return syscall


def _lifecycle():
    table = AgentTable()
    resources = AgentResourceRegistry()
    queue = KernelQueueStore()
    cleanup = AgentCleanupManager(resource_registry=resources, agent_table=table, queue_store=queue)
    lifecycle = AgentLifecycleManager(agent_table=table, resource_registry=resources, cleanup_manager=cleanup)
    return lifecycle, table, queue, cleanup


def test_queue_store_hold_by_agent_removes_without_event_set():
    queue = KernelQueueStore()
    first = _syscall("agent_1", "first")
    second = _syscall("agent_2", "second")
    queue.add(KernelQueueName.MEMORY, first)
    queue.add(KernelQueueName.MEMORY, second)

    held = queue.hold_by_agent("agent_1", reason="pause")

    assert held == [first]
    assert first.status == KernelSyscallStatus.SUSPENDED
    assert first.wait(timeout_s=0.01) is False
    assert queue.drain(KernelQueueName.MEMORY) == [second]


def test_queue_store_requeue_many_preserves_order():
    queue = KernelQueueStore()
    first = _syscall("agent_1", "first")
    second = _syscall("agent_1", "second")

    requeued = queue.requeue_many([first, second], reason="resume")

    assert requeued == [first.syscall_id, second.syscall_id]
    assert queue.get(KernelQueueName.MEMORY, timeout_s=0.01) is first
    assert queue.get(KernelQueueName.MEMORY, timeout_s=0.01) is second


def test_queue_store_cancel_by_agent_sets_cancelled_and_event():
    queue = KernelQueueStore()
    first = _syscall("agent_1", "first")
    second = _syscall("agent_2", "second")
    queue.add(KernelQueueName.MEMORY, first)
    queue.add(KernelQueueName.MEMORY, second)

    cancelled = queue.cancel_by_agent("agent_1", reason="kill")

    assert cancelled == [first]
    assert first.status == KernelSyscallStatus.CANCELLED
    assert first.wait(timeout_s=0.01) is True
    assert queue.drain(KernelQueueName.MEMORY) == [second]


def test_suspend_does_not_cancel_held_syscalls():
    lifecycle, table, queue, cleanup = _lifecycle()
    agent = lifecycle.create_agent_for_session(app_id="app_a", session_id="sess_1", agent_id="agent_1")
    lifecycle.start_agent(agent.agent_id)
    queued = _syscall(agent.agent_id, "first")
    queue.add(KernelQueueName.MEMORY, queued)
    table.attach_syscall(agent.agent_id, queued.syscall_id)

    result = lifecycle.suspend_agent(agent.agent_id, reason="operator")

    assert result.success is True
    assert table.require(agent.agent_id).status == AgentStatus.SUSPENDED
    assert queued.status == KernelSyscallStatus.SUSPENDED
    assert queued.error_code == ""
    assert queued.wait(timeout_s=0.01) is False
    assert cleanup.held_syscalls_for_agent(agent.agent_id) == [queued]


def test_kill_cancels_held_syscalls():
    lifecycle, table, queue, cleanup = _lifecycle()
    agent = lifecycle.create_agent_for_session(app_id="app_a", session_id="sess_1", agent_id="agent_1")
    lifecycle.start_agent(agent.agent_id)
    queued = _syscall(agent.agent_id, "first")
    queue.add(KernelQueueName.MEMORY, queued)
    table.attach_syscall(agent.agent_id, queued.syscall_id)
    lifecycle.suspend_agent(agent.agent_id)

    result = lifecycle.kill_agent(agent.agent_id)

    assert result.success is True
    assert queued.status == KernelSyscallStatus.CANCELLED
    assert queued.wait(timeout_s=0.01) is True
    assert cleanup.held_syscalls_for_agent(agent.agent_id) == []


def test_cleanup_manager_keeps_held_syscall_objects_until_resume_or_kill():
    lifecycle, table, queue, cleanup = _lifecycle()
    agent = lifecycle.create_agent_for_session(app_id="app_a", session_id="sess_1", agent_id="agent_1")
    lifecycle.start_agent(agent.agent_id)
    first = _syscall(agent.agent_id, "first")
    second = _syscall(agent.agent_id, "second")
    for syscall in (first, second):
        queue.add(KernelQueueName.MEMORY, syscall)
        table.attach_syscall(agent.agent_id, syscall.syscall_id)

    lifecycle.suspend_agent(agent.agent_id)

    assert cleanup.held_syscalls_for_agent(agent.agent_id) == [first, second]
    lifecycle.resume_agent(agent.agent_id)
    assert cleanup.held_syscalls_for_agent(agent.agent_id) == []
    assert queue.get(KernelQueueName.MEMORY, timeout_s=0.01) is first
    assert queue.get(KernelQueueName.MEMORY, timeout_s=0.01) is second
