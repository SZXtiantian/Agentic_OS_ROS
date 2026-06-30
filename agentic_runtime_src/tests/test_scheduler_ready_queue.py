from __future__ import annotations

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, PriorityKey, QueryType, ReadyQueue, ResourceRequest, TaskGraph, TaskNode
from agentic_os.kernel.system_call import KernelResponse
from agentic_os.kernel.system_call.executor import SyscallExecutionResult
from agentic_os.kernel.system_call.models import KernelSyscall


class RecordingKernelService:
    def __init__(self) -> None:
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        syscall = KernelSyscall.create(agent_name, "skill", query.operation_type, query.params)
        syscall.syscall_id = f"ksc_{query.metadata['node_id']}"
        syscall.target = "skill"
        return SyscallExecutionResult(
            syscall=syscall,
            response=KernelResponse.ok({"ok": True}, metadata={"audit_id": f"audit_{query.metadata['node_id']}"}, data={"ok": True}),
            success=True,
            metadata={"queue_name": "skill", "audit_id": f"audit_{query.metadata['node_id']}"},
        )


def test_ready_queue_returns_highest_priority_node_id():
    queue = ReadyQueue()
    queue.push("slow", PriorityKey(0, 0, 0, 1, 1, 0, 0, 0, 0, 1))
    queue.push("urgent", PriorityKey(10, 10, 0, 9, 1, 0, 0, 0, 0, 2))

    assert queue.pop_best() == "urgent"
    assert queue.pop_best() == "slow"
    assert queue.pop_best() is None


def test_scheduler_recomputes_ready_node_priority_before_dispatch():
    service = RecordingKernelService()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, kernel_service=service)
    low = TaskNode.create(
        node_id="low",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "first"},
        base_priority=1,
    )
    boosted = TaskNode.create(
        node_id="boosted",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "second"},
        base_priority=0,
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"low": low, "boosted": boosted},
    )

    response = scheduler.submit_graph(graph)
    assert response.success is True
    assert scheduler.ready_queue.snapshot()[0]["node_id"] == "low"

    boosted.base_priority = 100
    decisions = scheduler.tick(max_dispatch=1)

    assert decisions[0]["node_id"] == "boosted"
    assert service.calls[0][1].metadata["node_id"] == "boosted"


def test_scheduler_defers_ready_node_when_lane_capacity_is_full():
    sink = InMemoryKernelEventSink()
    service = RecordingKernelService()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, kernel_service=service, event_sink=sink)
    running = TaskNode.create(
        node_id="running_motion",
        task_graph_id="g_motion",
        user_goal_id="goal_motion",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"place": "hall"},
        base_priority=10,
    )
    waiting = TaskNode.create(
        node_id="waiting_motion",
        task_graph_id="g_motion",
        user_goal_id="goal_motion",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"place": "kitchen"},
        base_priority=9,
    )
    graph = TaskGraph.create(
        task_graph_id="g_motion",
        user_goal_id="goal_motion",
        root_goal="navigate twice",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"running_motion": running, "waiting_motion": waiting},
    )

    response = scheduler.submit_graph(graph)
    assert response.success is True
    scheduler.graph_store.mark_status("running_motion", "running")
    scheduler.ready_queue.remove("running_motion")

    decisions = scheduler.tick(max_dispatch=1)

    assert decisions == []
    assert service.calls == []
    assert scheduler.graph_store.get_node("waiting_motion").status == "ready"
    assert scheduler.ready_queue.snapshot()[0]["node_id"] == "waiting_motion"
    assert any(
        event.get("event_type") == "scheduler.node.blocked"
        and event.get("metadata", {}).get("node_id") == "waiting_motion"
        and event.get("metadata", {}).get("error_code") == "SCHEDULER_LANE_CAPACITY_FULL"
        for event in sink.recent(limit=20)
    )


def test_scheduler_clears_error_code_after_blocked_node_retries_successfully():
    service = RecordingKernelService()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, kernel_service=service)
    holder = TaskNode.create(
        node_id="holder",
        task_graph_id="g_holder",
        user_goal_id="goal_holder",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"place": "hall"},
        resources=[ResourceRequest("base", mode="exclusive", lease_ttl_ns=100_000_000_000)],
    )
    held = scheduler.resource_arbiter.try_acquire(holder)
    waiter = TaskNode.create(
        node_id="waiter",
        task_graph_id="g_waiter",
        user_goal_id="goal_waiter",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"place": "kitchen"},
        resources=[ResourceRequest("base", mode="exclusive", lease_ttl_ns=100_000_000_000)],
    )
    graph = TaskGraph.create(
        task_graph_id="g_waiter",
        user_goal_id="goal_waiter",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"waiter": waiter},
    )

    assert held.success is True
    response = scheduler.submit_graph(graph)
    first = scheduler.tick(max_dispatch=1)
    blocked = scheduler.graph_store.get_node("waiter")
    assert response.success is True
    assert first[0]["success"] is False
    assert first[0]["error_code"] == "SCHEDULER_RESOURCE_UNAVAILABLE"
    assert blocked.status == "blocked"
    assert blocked.error_code == "SCHEDULER_RESOURCE_UNAVAILABLE"

    scheduler.resource_arbiter.release(held.leases, reason="resource_available")
    second = scheduler.tick(max_dispatch=1)
    completed = scheduler.graph_store.get_node("waiter")

    assert second[0]["success"] is True
    assert second[0]["error_code"] == ""
    assert completed.status == "completed"
    assert completed.error_code == ""
