from __future__ import annotations

import time

from agentic_os.kernel.device_arbitration import DeviceArbiter
from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, QueryType, ResourceArbiter, ResourceRequest, SchedulerAudit, TaskGraph, TaskGraphStore, TaskNode
from agentic_os.kernel.system_call import KernelResponse
from agentic_os.kernel.system_call.executor import SyscallExecutionResult
from agentic_os.kernel.system_call.models import KernelSyscall
from agentic_runtime.kernel_service import KernelService


def _node(node_id: str, priority: int) -> TaskNode:
    return TaskNode.create(
        node_id=node_id,
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        base_priority=priority,
        resources=[ResourceRequest("base", mode="exclusive", lease_ttl_ns=100)],
    )


def test_resource_arbiter_conflict_ttl_and_priority_inheritance():
    arbiter = ResourceArbiter()
    holder = _node("holder", 1)
    waiter = _node("waiter", 10)
    waiter.effective_priority = 10

    first = arbiter.try_acquire(holder, at_ns=1)
    second = arbiter.try_acquire(waiter, at_ns=2)
    expired = arbiter.expire(200)

    assert first.success is True
    assert second.success is False
    assert first.leases[0].holder_inherited_priority == 10
    assert expired[0].status == "expired"


def test_resource_arbiter_applies_priority_inheritance_to_holder_task_node():
    store = TaskGraphStore()
    holder = _node("holder", 1)
    waiter = _node("waiter", 10)
    waiter.effective_priority = 10
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"holder": holder, "waiter": waiter},
    )
    store.add_graph(graph)
    initial_revision = store.revision
    arbiter = ResourceArbiter(graph_store=store)

    first = arbiter.try_acquire(holder, at_ns=1)
    second = arbiter.try_acquire(waiter, at_ns=2)
    stored_holder = store.get_node("holder")

    assert first.success is True
    assert second.success is False
    assert first.leases[0].holder_inherited_priority == 10
    assert stored_holder.inherited_priority == 10
    assert stored_holder.effective_priority == 10
    assert store.revision > initial_revision


def test_resource_arbiter_applies_priority_ceiling():
    arbiter = ResourceArbiter()
    node = _node("ceiling", 1)
    node.resources[0].priority_ceiling = 50

    result = arbiter.try_acquire(node, at_ns=1)

    assert result.success is True
    assert node.effective_priority == 50
    assert node.inherited_priority == 50


def test_resource_arbiter_acquires_and_releases_device_lock():
    device = DeviceArbiter()
    arbiter = ResourceArbiter(device_arbiter=device)
    node = _node("holder", 1)

    result = arbiter.try_acquire(node, at_ns=1)
    lease = result.leases[0]

    assert result.success is True
    assert device.status()["leases"]["base"]["owner"] == "holder"
    assert lease.metadata["device_owner"] == "holder"
    assert lease.metadata["device_lease_id"].startswith("lease_")

    release = arbiter.release(result.leases)

    assert release.success is True
    assert device.status()["leases"] == {}


def test_resource_arbiter_release_by_agent_surfaces_device_release_failure():
    class FailingReleaseDevice:
        def acquire(self, resource, owner, reason=""):
            return {"success": True, "lease": {"lease_id": f"lease_{resource}", "owner": owner}}

        def release(self, resource, owner):
            return {"success": False, "error_code": "DEVICE_RELEASE_FAILED", "resource": resource, "owner": owner}

    arbiter = ResourceArbiter(device_arbiter=FailingReleaseDevice())
    node = _node("holder", 1)

    acquire = arbiter.try_acquire(node, at_ns=1)
    release = arbiter.release_by_agent("agent", reason="agent_killed")

    assert acquire.success is True
    assert release.success is False
    assert release.error_code == "SCHEDULER_RESOURCE_RELEASE_FAILED"
    assert release.metadata["resource_lease_id"] == acquire.leases[0].lease_id
    assert arbiter.snapshot()["leases"][acquire.leases[0].lease_id]["status"] == "acquired"


def test_resource_arbiter_rolls_back_device_locks_when_later_resource_is_busy():
    device = DeviceArbiter()
    device.acquire("arm", "other_owner", reason="existing")
    node = _node("holder", 1)
    node.resources = [
        ResourceRequest("base", mode="exclusive", lease_ttl_ns=100),
        ResourceRequest("arm", mode="exclusive", lease_ttl_ns=100),
    ]
    arbiter = ResourceArbiter(device_arbiter=device)

    result = arbiter.try_acquire(node, at_ns=1)

    assert result.success is False
    assert result.error_code == "SCHEDULER_RESOURCE_UNAVAILABLE"
    assert result.metadata["upstream_error_code"] == "DEVICE_RESOURCE_BUSY"
    assert "base" not in device.status()["leases"]
    assert device.status()["leases"]["arm"]["owner"] == "other_owner"
    assert arbiter.snapshot()["leases"] == {}


def test_resource_lease_binds_real_syscall_id_back_to_acb_handle():
    class Config:
        scheduler_policy = "fifo"
        storage_root = "/tmp/agentic_scheduler_resource_bind"
        kernel = {"scheduler_policy": "fifo"}

    service = KernelService(config=Config())
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_resource_bind")
    service.start_agent(agent.agent_id)
    arbiter = ResourceArbiter(agent_lifecycle=service.agent_lifecycle)
    node = TaskNode.create(
        node_id="node_bind",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id=agent.agent_id,
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        resources=[ResourceRequest("base", mode="exclusive", lease_ttl_ns=100_000_000)],
    )

    result = arbiter.try_acquire(node, at_ns=1)
    arbiter.bind_syscall(node, "ksc_real")
    handle = service.agent_resources.get(result.leases[0].agent_resource_handle_id)

    assert result.success is True
    assert handle is not None
    assert handle.syscall_id == "ksc_real"
    assert handle.lease_id == result.leases[0].lease_id


class SuccessfulKernelService:
    def execute_request(self, agent_name, query, timeout_s=None):
        syscall = KernelSyscall.create(agent_name, "robot_motion", query.operation_type, query.params)
        syscall.syscall_id = "ksc_real_motion"
        syscall.target = "robot_motion"
        return SyscallExecutionResult(
            syscall=syscall,
            response=KernelResponse.ok({"ok": True, "audit_id": "audit_real"}, metadata={"audit_id": "audit_real"}, data={"ok": True}),
            success=True,
            metadata={"queue_name": "robot_motion", "audit_id": "audit_real"},
        )


class SlowSuccessfulKernelService(SuccessfulKernelService):
    def execute_request(self, agent_name, query, timeout_s=None):
        time.sleep(0.001)
        return super().execute_request(agent_name, query, timeout_s=timeout_s)


class FailingReleaseDevice:
    def acquire(self, resource, owner, reason=""):
        return {"success": True, "lease": {"lease_id": f"lease_{resource}", "owner": owner}}

    def release(self, resource, owner):
        return {"success": False, "error_code": "DEVICE_RELEASE_FAILED", "resource": resource, "owner": owner}


def test_resource_expiration_surfaces_release_failure_and_keeps_resource_blocked():
    sink = InMemoryKernelEventSink()
    arbiter = ResourceArbiter(audit=SchedulerAudit(event_sink=sink), device_arbiter=FailingReleaseDevice())
    holder = _node("holder", 1)
    waiter = _node("waiter", 10)

    acquire = arbiter.try_acquire(holder, at_ns=1)
    expired = arbiter.expire(200)
    blocked = arbiter.try_acquire(waiter, at_ns=201)
    snapshot = arbiter.snapshot()
    events = sink.recent(limit=40)

    assert acquire.success is True
    assert expired == [acquire.leases[0]]
    assert expired[0].status == "release_failed"
    assert expired[0].metadata["expiration_error_code"] == "SCHEDULER_RESOURCE_RELEASE_FAILED"
    assert blocked.success is False
    assert blocked.error_code == "SCHEDULER_RESOURCE_UNAVAILABLE"
    assert snapshot["leases"][acquire.leases[0].lease_id]["status"] == "release_failed"
    assert acquire.leases[0].lease_id not in snapshot["expired_leases"]
    assert any(
        event["event_type"] == "scheduler.resource.lease_release_failed"
        and event["metadata"]["error_code"] == "SCHEDULER_RESOURCE_RELEASE_FAILED"
        and event["metadata"]["reason"] == "lease_expired"
        for event in events
    )
    assert any(
        event["event_type"] == "scheduler.resource.lease_expired"
        and event["metadata"]["cleanup_error_code"] == "SCHEDULER_RESOURCE_RELEASE_FAILED"
        for event in events
    )


def test_scheduler_tick_marks_node_failed_when_expired_lease_release_fails():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(event_sink=sink),
        {},
        event_sink=sink,
        device_arbiter=FailingReleaseDevice(),
    )
    node = TaskNode.create(
        node_id="ttl_release_failure_node",
        task_graph_id="g_ttl_release_failure",
        user_goal_id="goal_ttl_release_failure",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        resources=[ResourceRequest("base", mode="exclusive", lease_ttl_ns=1)],
    )
    graph = TaskGraph.create(
        task_graph_id="g_ttl_release_failure",
        user_goal_id="goal_ttl_release_failure",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={node.node_id: node},
    )

    assert scheduler.submit_graph(graph).success is True
    stored = scheduler.graph_store.get_node(node.node_id)
    lease_result = scheduler.resource_arbiter.try_acquire(stored, at_ns=1)
    assert lease_result.success is True
    scheduler.graph_store.mark_status(node.node_id, "running")
    scheduler.ready_queue.remove(node.node_id)

    assert scheduler.tick(max_dispatch=0) == []
    stored = scheduler.graph_store.get_node(node.node_id)
    events = sink.recent(limit=80)

    assert stored.status == "failed"
    assert stored.error_code == "SCHEDULER_RESOURCE_RELEASE_FAILED"
    assert scheduler.resource_arbiter.snapshot()["leases"][lease_result.leases[0].lease_id]["status"] == "release_failed"
    assert any(
        event["event_type"] == "scheduler.node.failed"
        and event["metadata"]["node_id"] == node.node_id
        and event["metadata"]["error_code"] == "SCHEDULER_RESOURCE_RELEASE_FAILED"
        and event["metadata"]["cleanup_error_code"] == "SCHEDULER_RESOURCE_RELEASE_FAILED"
        for event in events
    )


def test_scheduler_marks_node_stale_when_dispatch_outlives_resource_lease_ttl():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(event_sink=sink),
        {},
        kernel_service=SlowSuccessfulKernelService(),
        event_sink=sink,
    )
    node = TaskNode.create(
        node_id="slow_ttl_node",
        task_graph_id="g_slow_ttl",
        user_goal_id="goal_slow_ttl",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"place": "hall"},
        resources=[ResourceRequest("base", mode="exclusive", lease_ttl_ns=1)],
    )
    graph = TaskGraph.create(
        task_graph_id="g_slow_ttl",
        user_goal_id="goal_slow_ttl",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={node.node_id: node},
    )

    assert scheduler.submit_graph(graph).success is True
    decision = scheduler.tick(max_dispatch=1)[0]
    stored = scheduler.graph_store.get_node(node.node_id)
    events = sink.recent(limit=80)
    expired_leases = scheduler.resource_arbiter.snapshot()["expired_leases"]

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_RESOURCE_LEASE_EXPIRED"
    assert stored.status == "stale"
    assert stored.error_code == "SCHEDULER_RESOURCE_LEASE_EXPIRED"
    assert expired_leases
    assert any(
        event["event_type"] == "scheduler.resource.lease_expired"
        and event["metadata"]["app_id"] == "app"
        and event["metadata"]["session_id"] == "sess"
        and event["metadata"]["task_graph_id"] == "g_slow_ttl"
        and event["metadata"]["error_code"] == "SCHEDULER_RESOURCE_LEASE_EXPIRED"
        for event in events
    )
    assert any(
        event["event_type"] == "scheduler.node.stale"
        and event["metadata"]["node_id"] == node.node_id
        and event["metadata"]["error_code"] == "SCHEDULER_RESOURCE_LEASE_EXPIRED"
        and event["metadata"]["dispatch_success"] is True
        for event in events
    )


def test_scheduler_marks_node_failed_when_dispatch_resource_release_fails():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(event_sink=sink),
        {},
        kernel_service=SuccessfulKernelService(),
        event_sink=sink,
        device_arbiter=FailingReleaseDevice(),
    )
    node = TaskNode.create(
        node_id="release_failure_node",
        task_graph_id="g_release_failure",
        user_goal_id="goal_release_failure",
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
    graph = TaskGraph.create(
        task_graph_id="g_release_failure",
        user_goal_id="goal_release_failure",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={node.node_id: node},
    )

    assert scheduler.submit_graph(graph).success is True
    decision = scheduler.tick(max_dispatch=1)[0]
    stored = scheduler.graph_store.get_node(node.node_id)
    events = sink.recent(limit=80)

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_RESOURCE_RELEASE_FAILED"
    assert stored.status == "failed"
    assert stored.error_code == "SCHEDULER_RESOURCE_RELEASE_FAILED"
    assert any(event["event_type"] == "scheduler.resource.lease_release_failed" for event in events)
    assert any(
        event["event_type"] == "scheduler.node.failed"
        and event["metadata"]["node_id"] == node.node_id
        and event["metadata"]["error_code"] == "SCHEDULER_RESOURCE_RELEASE_FAILED"
        and event["metadata"]["prior_error_code"] == ""
        for event in events
    )
    assert any(lease["status"] == "acquired" for lease in scheduler.resource_arbiter.snapshot()["leases"].values())


def test_scheduler_audits_missing_dispatch_dependency_as_node_failure():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, event_sink=sink)
    node = TaskNode.create(
        node_id="no_dispatch_adapter",
        task_graph_id="g_no_dispatch_adapter",
        user_goal_id="goal_no_dispatch_adapter",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "hello"},
    )
    graph = TaskGraph.create(
        task_graph_id="g_no_dispatch_adapter",
        user_goal_id="goal_no_dispatch_adapter",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={node.node_id: node},
    )

    assert scheduler.submit_graph(graph).success is True
    decision = scheduler.tick(max_dispatch=1)[0]

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE"
    assert any(
        event["event_type"] == "scheduler.node.failed"
        and event["metadata"]["node_id"] == node.node_id
        and event["metadata"]["error_code"] == "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE"
        for event in sink.recent(limit=40)
    )
