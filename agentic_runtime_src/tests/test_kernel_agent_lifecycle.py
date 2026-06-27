from agentic_os.kernel.agent import (
    AGENT_KILL_REQUESTED,
    AGENT_NOT_RUNNABLE,
    AGENT_REAP_FORBIDDEN,
    AGENT_SUSPENDED,
    AgentCleanupManager,
    AgentLifecycleManager,
    AgentResourceRegistry,
    AgentStatus,
    AgentTable,
)
from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore
from agentic_os.kernel.system_call import KernelSyscall, KernelSyscallStatus


def _build():
    table = AgentTable()
    resources = AgentResourceRegistry()
    queue = KernelQueueStore()
    cleanup = AgentCleanupManager(resource_registry=resources, agent_table=table, queue_store=queue)
    lifecycle = AgentLifecycleManager(agent_table=table, resource_registry=resources, cleanup_manager=cleanup)
    return lifecycle, table, resources, queue


def _ready_agent(lifecycle):
    agent = lifecycle.create_agent_for_session(app_id="app_a", session_id="sess_1", agent_id="agent_1")
    lifecycle.start_agent(agent.agent_id)
    return agent


def _queued_syscall(agent_id: str) -> KernelSyscall:
    syscall = KernelSyscall.create("app_a", KernelQueueName.MEMORY, "remember")
    syscall.agent_id = agent_id
    syscall.aid = agent_id
    syscall.queue_name = KernelQueueName.MEMORY
    return syscall


def test_create_agent_for_session_starts_created():
    lifecycle, _, _, _ = _build()

    agent = lifecycle.create_agent_for_session(app_id="app_a", session_id="sess_1")

    assert agent.status == AgentStatus.CREATED
    assert agent.created_by == "session_runner"


def test_start_agent_moves_created_to_ready():
    lifecycle, _, _, _ = _build()
    agent = lifecycle.create_agent(app_id="app_a", session_id="sess_1", agent_id="agent_1")

    result = lifecycle.start_agent(agent.agent_id)

    assert result.success is True
    assert agent.status == AgentStatus.READY


def test_ready_agent_admits_syscall():
    lifecycle, _, _, _ = _build()
    agent = _ready_agent(lifecycle)

    decision = lifecycle.admit_syscall(agent_id=agent.agent_id, operation_type="mem_remember")

    assert decision.success is True


def test_created_agent_rejects_syscall():
    lifecycle, _, _, _ = _build()
    agent = lifecycle.create_agent(app_id="app_a", session_id="sess_1", agent_id="agent_1")

    decision = lifecycle.admit_syscall(agent_id=agent.agent_id, operation_type="mem_remember")

    assert decision.success is False
    assert decision.error_code == AGENT_NOT_RUNNABLE


def test_suspended_agent_rejects_new_syscall():
    lifecycle, _, _, _ = _build()
    agent = _ready_agent(lifecycle)
    lifecycle.suspend_agent(agent.agent_id)

    decision = lifecycle.admit_syscall(agent_id=agent.agent_id, operation_type="mem_remember")

    assert decision.success is False
    assert decision.error_code == AGENT_SUSPENDED


def test_killed_agent_rejects_new_syscall():
    lifecycle, _, _, _ = _build()
    agent = _ready_agent(lifecycle)
    lifecycle.kill_agent(agent.agent_id)

    decision = lifecycle.admit_syscall(agent_id=agent.agent_id, operation_type="mem_remember")

    assert decision.success is False
    assert decision.error_code == AGENT_KILL_REQUESTED or decision.error_code == "AGENT_TERMINAL"


def test_suspend_agent_holds_queued_syscalls_without_cancelling():
    lifecycle, table, _, queue = _build()
    agent = _ready_agent(lifecycle)
    syscall = _queued_syscall(agent.agent_id)
    queue.add(KernelQueueName.MEMORY, syscall)
    table.attach_syscall(agent.agent_id, syscall.syscall_id)

    result = lifecycle.suspend_agent(agent.agent_id)

    assert result.held_syscalls == [syscall.syscall_id]
    assert syscall.status == KernelSyscallStatus.SUSPENDED
    assert syscall.error_code == ""
    assert syscall.wait(timeout_s=0.01) is False


def test_resume_agent_requeues_held_syscalls():
    lifecycle, table, _, queue = _build()
    agent = _ready_agent(lifecycle)
    syscall = _queued_syscall(agent.agent_id)
    queue.add(KernelQueueName.MEMORY, syscall)
    table.attach_syscall(agent.agent_id, syscall.syscall_id)
    lifecycle.suspend_agent(agent.agent_id)

    result = lifecycle.resume_agent(agent.agent_id)

    assert result.success is True
    assert result.resumed_syscalls == [syscall.syscall_id]
    assert table.require(agent.agent_id).status == AgentStatus.READY
    assert queue.get(KernelQueueName.MEMORY, timeout_s=0.01) is syscall


def test_kill_agent_cancels_queued_and_held_syscalls():
    lifecycle, table, _, queue = _build()
    agent = _ready_agent(lifecycle)
    queued = _queued_syscall(agent.agent_id)
    held = _queued_syscall(agent.agent_id)
    queue.add(KernelQueueName.MEMORY, queued)
    queue.add(KernelQueueName.MEMORY, held)
    table.attach_syscall(agent.agent_id, queued.syscall_id)
    table.attach_syscall(agent.agent_id, held.syscall_id)
    lifecycle.suspend_agent(agent.agent_id)

    result = lifecycle.kill_agent(agent.agent_id)

    assert result.success is True
    assert set(result.cancelled_syscalls) == {queued.syscall_id, held.syscall_id}
    assert queued.status == KernelSyscallStatus.CANCELLED
    assert held.status == KernelSyscallStatus.CANCELLED


def test_exit_agent_marks_exited_and_cleanup_completed():
    lifecycle, _, _, _ = _build()
    agent = _ready_agent(lifecycle)

    result = lifecycle.exit_agent(agent.agent_id)

    assert result.success is True
    assert agent.status == AgentStatus.EXITED
    assert agent.cleanup_status == "completed"


def test_fail_agent_marks_failed():
    lifecycle, _, _, _ = _build()
    agent = _ready_agent(lifecycle)

    result = lifecycle.fail_agent(agent.agent_id, reason="bad result", error_code="APP_RESULT_INVALID")

    assert result.success is True
    assert agent.status == AgentStatus.FAILED
    assert agent.error_code == "APP_RESULT_INVALID"


def test_crash_agent_marks_crashed_and_runs_cleanup():
    lifecycle, table, _, queue = _build()
    agent = _ready_agent(lifecycle)
    syscall = _queued_syscall(agent.agent_id)
    queue.add(KernelQueueName.MEMORY, syscall)
    table.attach_syscall(agent.agent_id, syscall.syscall_id)

    result = lifecycle.crash_agent(agent.agent_id, reason="boom", error_code="APP_EXCEPTION")

    assert result.success is True
    assert agent.status == AgentStatus.CRASHED
    assert syscall.status == KernelSyscallStatus.CANCELLED
    assert agent.cleanup_status == "completed"


def test_reap_requires_terminal_agent():
    lifecycle, _, _, _ = _build()
    agent = _ready_agent(lifecycle)

    result = lifecycle.reap_agent(agent.agent_id)

    assert result.success is False
    assert result.error_code == AGENT_REAP_FORBIDDEN


def test_reap_moves_agent_to_tombstone():
    lifecycle, table, _, _ = _build()
    agent = _ready_agent(lifecycle)
    lifecycle.exit_agent(agent.agent_id)

    result = lifecycle.reap_agent(agent.agent_id)

    assert result.success is True
    assert table.get(agent.agent_id) is None
    assert table.get(agent.agent_id, include_reaped=True).status == AgentStatus.REAPED
