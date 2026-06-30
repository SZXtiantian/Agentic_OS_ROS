from __future__ import annotations

from agentic_os.kernel.agent.models import AgentResourceState
from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueName
from agentic_os.kernel.scheduler import PreemptPolicy, QueryType, ResourceRequest, TaskGraph, TaskNode
from agentic_os.kernel.scheduler.dispatch import DispatchResult
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall, RobotCapabilityQuery
from agentic_runtime.kernel_service import KernelService


class Config:
    scheduler_policy = "fifo"
    storage_root = "/tmp/agentic_scheduler_acb"
    kernel = {"scheduler_policy": "env_aware_priority_dag"}


def test_scheduler_lifecycle_hooks_suspend_resume_and_kill_nodes():
    service = KernelService(config=Config())
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_acb")
    service.start_agent(agent.agent_id)
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id=agent.agent_id,
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="report",
        agent_id=agent.agent_id,
        app_id="app",
        session_id="sess",
        nodes={"n": node},
    )
    service.scheduler.submit_graph(graph)

    assert service.scheduler.graph_store.get_node("n").status == "ready"
    service.suspend_agent(agent.agent_id)
    assert service.scheduler.graph_store.get_node("n").status == "suspended"
    assert service.scheduler.graph_store.get_graph("g").status == "partially_suspended"
    service.resume_agent(agent.agent_id)
    assert service.scheduler.graph_store.get_node("n").status == "ready"
    assert service.scheduler.graph_store.get_graph("g").status == "admitted"
    service.kill_agent(agent.agent_id)
    assert service.scheduler.graph_store.get_node("n").status == "cancelled"
    assert service.scheduler.graph_store.get_graph("g").status == "cancelled"
    service.stop()


def test_scheduler_blocks_unknown_agent_before_node_can_run():
    sink = InMemoryKernelEventSink()
    service = KernelService(config=Config(), event_sink=sink)
    node = TaskNode.create(
        node_id="unknown_agent_node",
        task_graph_id="g_unknown_agent",
        user_goal_id="goal_unknown_agent",
        agent_id="missing_agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id="g_unknown_agent",
        user_goal_id="goal_unknown_agent",
        root_goal="report",
        agent_id="missing_agent",
        app_id="app",
        session_id="sess",
        nodes={"unknown_agent_node": node},
    )

    response = service.scheduler.submit_graph(graph)
    stored = service.scheduler.graph_store.get_node("unknown_agent_node")
    events = sink.recent(limit=50)

    assert response.success is True
    assert stored.status == "blocked"
    assert stored.error_code == "SCHEDULER_AGENT_NOT_RUNNABLE"
    assert any(
        event["event_type"] == "scheduler.node.blocked"
        and event["metadata"]["node_id"] == "unknown_agent_node"
        and event["metadata"]["error_code"] == "SCHEDULER_AGENT_NOT_RUNNABLE"
        and event["metadata"]["upstream_error_code"] == "AGENT_NOT_FOUND"
        for event in events
    )
    service.stop()


def test_scheduler_fails_node_when_dispatch_returns_unbound_syscall():
    class UnboundDispatchAdapter:
        def dispatch(self, node, leases, *, scheduler_revision, timeout_s=None):
            return DispatchResult(
                True,
                syscall_id="ksc_unbound",
                syscall_agent_id="",
                response=KernelResponse.ok({"ok": True}),
                metadata={"queue_name": "background"},
            )

    sink = InMemoryKernelEventSink()
    service = KernelService(config=Config(), event_sink=sink)
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_unbound_dispatch")
    service.start_agent(agent.agent_id)
    service.scheduler.dispatch_adapter = UnboundDispatchAdapter()
    node = TaskNode.create(
        node_id="unbound_dispatch_node",
        task_graph_id="g_unbound_dispatch",
        user_goal_id="goal_unbound_dispatch",
        agent_id=agent.agent_id,
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id="g_unbound_dispatch",
        user_goal_id="goal_unbound_dispatch",
        root_goal="report",
        agent_id=agent.agent_id,
        app_id="app",
        session_id="sess",
        nodes={"unbound_dispatch_node": node},
    )

    assert service.scheduler.submit_graph(graph).success is True
    decision = service.scheduler.tick(max_dispatch=1)[0]
    stored = service.scheduler.graph_store.get_node("unbound_dispatch_node")
    events = sink.recent(limit=80)

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_AGENT_NOT_RUNNABLE"
    assert stored.status == "failed"
    assert stored.error_code == "SCHEDULER_AGENT_NOT_RUNNABLE"
    assert any(
        event["event_type"] == "scheduler.node.failed"
        and event["metadata"]["node_id"] == "unbound_dispatch_node"
        and event["metadata"]["error_code"] == "SCHEDULER_AGENT_NOT_RUNNABLE"
        and event["metadata"]["syscall_id"] == "ksc_unbound"
        for event in events
    )
    service.stop()


def test_scheduler_suspend_preempts_cancellable_running_node():
    class RecordingKernelService:
        def __init__(self):
            self.cancelled = []

        def cancel_request(self, syscall_id):
            self.cancelled.append(syscall_id)
            from agentic_os.kernel.system_call import KernelResponse

            return KernelResponse.ok({"cancelled": [syscall_id]})

    service = KernelService(config=Config())
    scheduler = service.scheduler
    scheduler.preemption.kernel_service = RecordingKernelService()
    scheduler.lifecycle_hooks.preemption_manager = scheduler.preemption
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_running_suspend")
    service.start_agent(agent.agent_id)
    node = TaskNode.create(
        node_id="running",
        task_graph_id="g_running",
        user_goal_id="goal",
        agent_id=agent.agent_id,
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="llm.plan",
        query_type=QueryType.LLM,
        preempt_policy=PreemptPolicy.CANCELLABLE,
        syscall_id="ksc_running",
    )
    graph = TaskGraph.create(
        task_graph_id="g_running",
        user_goal_id="goal",
        root_goal="plan",
        agent_id=agent.agent_id,
        app_id="app",
        session_id="sess",
        nodes={"running": node},
    )
    scheduler.submit_graph(graph)
    scheduler.graph_store.mark_status("running", "running")

    scheduler.on_agent_suspended(agent.agent_id, reason="operator_requested")

    assert scheduler.graph_store.get_node("running").status == "suspended"
    assert scheduler.preemption.kernel_service.cancelled == ["ksc_running"]
    service.stop()


def test_scheduler_suspend_audits_blocked_running_node_when_preemption_rejected():
    sink = InMemoryKernelEventSink()
    service = KernelService(config=Config(), event_sink=sink)
    scheduler = service.scheduler
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_running_blocked_suspend")
    service.start_agent(agent.agent_id)
    node = TaskNode.create(
        node_id="running_blocked",
        task_graph_id="g_running_blocked",
        user_goal_id="goal",
        agent_id=agent.agent_id,
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        preempt_policy=PreemptPolicy.NON_PREEMPTIBLE,
        syscall_id="ksc_running_blocked",
    )
    graph = TaskGraph.create(
        task_graph_id="g_running_blocked",
        user_goal_id="goal",
        root_goal="navigate",
        agent_id=agent.agent_id,
        app_id="app",
        session_id="sess",
        nodes={"running_blocked": node},
    )
    scheduler.submit_graph(graph)
    scheduler.graph_store.mark_status("running_blocked", "running")

    scheduler.on_agent_suspended(agent.agent_id, reason="operator_requested")
    blocked = scheduler.graph_store.get_node("running_blocked")
    events = sink.recent(limit=80)

    assert blocked.status == "blocked"
    assert blocked.error_code == "SCHEDULER_PREEMPTION_UNSUPPORTED"
    assert any(
        event["event_type"] == "scheduler.preemption.rejected"
        and event["metadata"]["app_id"] == "app"
        and event["metadata"]["session_id"] == "sess"
        and event["metadata"]["task_graph_id"] == "g_running_blocked"
        and event["metadata"]["syscall_id"] == "ksc_running_blocked"
        for event in events
    )
    assert any(
        event["event_type"] == "scheduler.node.blocked"
        and event["metadata"]["node_id"] == "running_blocked"
        and event["metadata"]["error_code"] == "SCHEDULER_PREEMPTION_UNSUPPORTED"
        and event["metadata"]["app_id"] == "app"
        and event["metadata"]["session_id"] == "sess"
        and event["metadata"]["task_graph_id"] == "g_running_blocked"
        for event in events
    )
    service.stop()


def test_scheduler_suspend_checkpointable_running_node_preserves_real_checkpoint(tmp_path):
    import threading

    class Config:
        scheduler_policy = "fifo"
        storage_root = tmp_path / "storage"
        kernel = {"scheduler_policy": "env_aware_priority_dag"}

    class CheckpointRobotSensorManager:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.active_syscall = None

        def address_request(self, syscall):
            self.active_syscall = syscall
            self.started.set()
            self.release.wait(timeout=2.0)
            return {"success": False, "error_code": "ROBOT_CAPABILITY_INTERRUPTED"}

        def checkpoint_request(self, syscall, **metadata):
            self.release.set()
            return KernelResponse.ok(
                {
                    "checkpoint_id": "inspect_suspend_cp",
                    "partial_result": {"visited_waypoints": ["north_hall"]},
                    "completed_coverage": ["zone_north"],
                },
                data={
                    "checkpoint_id": "inspect_suspend_cp",
                    "partial_result": {"visited_waypoints": ["north_hall"]},
                    "completed_coverage": ["zone_north"],
                },
            )

    sink = InMemoryKernelEventSink()
    manager = CheckpointRobotSensorManager()
    service = KernelService(config=Config(), managers={"robot_sensor": manager}, event_sink=sink)
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_checkpoint_suspend")
    service.start_agent(agent.agent_id)
    service.start()
    result_holder = {}
    try:
        def submit_request():
            result_holder["result"] = service.execute_request(
                "app",
                RobotCapabilityQuery(
                    operation_type="robot.inspect_area",
                    skill_name="robot.inspect_area",
                    app_id="app",
                    session_id="sess",
                    metadata={
                        "agent_id": agent.agent_id,
                        "app_id": "app",
                        "session_id": "sess",
                    },
                ),
                timeout_s=2.0,
            )

        thread = threading.Thread(target=submit_request)
        thread.start()
        assert manager.started.wait(timeout=2.0)
        syscall = manager.active_syscall
        assert syscall is not None
        node = TaskNode.create(
            node_id="checkpoint_running",
            task_graph_id="g_checkpoint_running",
            user_goal_id="goal",
            agent_id=agent.agent_id,
            agent_name="app",
            app_id="app",
            session_id="sess",
            capability="robot.inspect_area",
            operation_type="robot.inspect_area",
            query_type=QueryType.ROBOT_CAPABILITY,
            preempt_policy=PreemptPolicy.CHECKPOINTABLE,
            syscall_id=syscall.syscall_id,
        )
        graph = TaskGraph.create(
            task_graph_id="g_checkpoint_running",
            user_goal_id="goal",
            root_goal="inspect",
            agent_id=agent.agent_id,
            app_id="app",
            session_id="sess",
            nodes={"checkpoint_running": node},
        )
        service.scheduler.submit_graph(graph)
        service.scheduler.graph_store.mark_status("checkpoint_running", "running")

        response = service.suspend_agent(agent.agent_id, reason="operator_pause")
        thread.join(timeout=2.0)
        recovered = service.context.recover("sess", "app", checkpoint="inspect_suspend_cp")
        stored_node = service.scheduler.graph_store.get_node("checkpoint_running")

        assert response.success is True
        assert stored_node.status == "suspended"
        assert stored_node.metadata["checkpoint"]["checkpoint_id"] == "inspect_suspend_cp"
        assert stored_node.metadata["checkpoint"]["completed_coverage"] == ["zone_north"]
        assert recovered is not None
        assert recovered.state["completed_coverage"] == ["zone_north"]
        assert any(
            event["event_type"] == "scheduler.preemption.accepted"
            and event["metadata"]["checkpoint_saved"] is True
            for event in sink.recent(limit=80)
        )
    finally:
        manager.release.set()
        service.stop()


def test_scheduler_suspend_releases_preempted_running_node_leases_from_acb():
    class RecordingKernelService:
        def __init__(self):
            self.cancelled = []

        def cancel_request(self, syscall_id):
            self.cancelled.append(syscall_id)
            from agentic_os.kernel.system_call import KernelResponse

            return KernelResponse.ok({"cancelled": [syscall_id]})

    service = KernelService(config=Config())
    scheduler = service.scheduler
    scheduler.preemption.kernel_service = RecordingKernelService()
    scheduler.lifecycle_hooks.preemption_manager = scheduler.preemption
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_running_lease_suspend")
    service.start_agent(agent.agent_id)
    node = TaskNode.create(
        node_id="running_with_lease",
        task_graph_id="g_running_lease",
        user_goal_id="goal",
        agent_id=agent.agent_id,
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="llm.plan",
        query_type=QueryType.LLM,
        preempt_policy=PreemptPolicy.CANCELLABLE,
        syscall_id="ksc_running_lease",
        resources=[ResourceRequest("llm_context", mode="exclusive", lease_ttl_ns=100_000_000_000)],
    )
    graph = TaskGraph.create(
        task_graph_id="g_running_lease",
        user_goal_id="goal",
        root_goal="plan",
        agent_id=agent.agent_id,
        app_id="app",
        session_id="sess",
        nodes={"running_with_lease": node},
    )
    scheduler.submit_graph(graph)
    lease_result = scheduler.resource_arbiter.try_acquire(node, at_ns=1)
    scheduler.graph_store.mark_status("running_with_lease", "running")

    scheduler.on_agent_suspended(agent.agent_id, reason="operator_requested")
    handle = service.agent_resources.get(lease_result.leases[0].agent_resource_handle_id)

    assert lease_result.success is True
    assert scheduler.resource_arbiter.snapshot()["leases"] == {}
    assert node.resource_lease_ids == []
    assert handle is not None
    assert handle.state == AgentResourceState.RELEASED
    assert scheduler.graph_store.get_node("running_with_lease").status == "suspended"
    assert scheduler.graph_store.get_graph("g_running_lease").status == "partially_suspended"
    service.stop()


def test_scheduler_lifecycle_audits_held_and_resumed_queued_syscalls():
    sink = InMemoryKernelEventSink()
    service = KernelService(config=Config(), event_sink=sink)
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_queue_suspend")
    service.start_agent(agent.agent_id)
    syscall = KernelSyscall.create("app", KernelQueueName.MEMORY, "memory.recall")
    syscall.agent_id = agent.agent_id
    syscall.aid = agent.agent_id
    syscall.queue_name = KernelQueueName.MEMORY
    service.queue_store.add(KernelQueueName.MEMORY, syscall)

    suspend_response = service.suspend_agent(agent.agent_id, reason="operator_pause")

    assert suspend_response.success is True
    assert suspend_response.data["held_syscalls"] == [syscall.syscall_id]
    assert service.queue_store.size(KernelQueueName.MEMORY) == 0
    assert any(
        event.get("event_type") == "scheduler.agent.suspended"
        and event.get("metadata", {}).get("held_syscall_ids") == [syscall.syscall_id]
        for event in sink.recent(limit=50)
    )

    resume_response = service.resume_agent(agent.agent_id, reason="operator_resume")

    assert resume_response.success is True
    assert resume_response.data["resumed_syscalls"] == [syscall.syscall_id]
    assert service.queue_store.size(KernelQueueName.MEMORY) == 1
    assert any(
        event.get("event_type") == "scheduler.agent.resumed"
        and event.get("metadata", {}).get("resumed_syscall_ids") == [syscall.syscall_id]
        for event in sink.recent(limit=50)
    )
    service.stop()


def test_scheduler_terminal_audits_cancelled_queued_syscalls():
    sink = InMemoryKernelEventSink()
    service = KernelService(config=Config(), event_sink=sink)
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_queue_kill")
    service.start_agent(agent.agent_id)
    syscall = KernelSyscall.create("app", KernelQueueName.MEMORY, "memory.recall")
    syscall.agent_id = agent.agent_id
    syscall.aid = agent.agent_id
    syscall.queue_name = KernelQueueName.MEMORY
    service.queue_store.add(KernelQueueName.MEMORY, syscall)

    response = service.kill_agent(agent.agent_id, reason="operator_kill")

    assert response.success is True
    assert response.data["cancelled_syscalls"] == [syscall.syscall_id]
    assert service.queue_store.size(KernelQueueName.MEMORY) == 0
    assert syscall.event.is_set()
    assert any(
        event.get("event_type") == "scheduler.agent.killed"
        and event.get("metadata", {}).get("cancelled_syscall_ids") == [syscall.syscall_id]
        for event in sink.recent(limit=50)
    )
    service.stop()


def test_scheduler_exit_cancels_unfinished_dag_without_fake_completion():
    sink = InMemoryKernelEventSink()
    service, agent = _service_with_ready_graph("agent_exit", sink=sink)

    response = service.exit_agent(agent.agent_id, reason="app_completed")

    assert response.success is True
    assert service.scheduler.graph_store.get_node("n_agent_exit").status == "cancelled"
    assert service.scheduler.graph_store.get_node("n_agent_exit").error_code == "SCHEDULER_AGENT_EXITED"
    assert service.scheduler.graph_store.get_graph("g_agent_exit").status == "cancelled"
    assert any(
        event.get("event_type") == "scheduler.node.cancelled"
        and event.get("metadata", {}).get("lifecycle_event") == "exited"
        for event in sink.recent(limit=50)
    )
    service.stop()


def test_scheduler_fail_agent_marks_unfinished_dag_failed():
    sink = InMemoryKernelEventSink()
    service, agent = _service_with_ready_graph("agent_failed", sink=sink)

    response = service.fail_agent(agent.agent_id, reason="bad_result", error_code="APP_RESULT_INVALID")

    assert response.success is True
    assert service.scheduler.graph_store.get_node("n_agent_failed").status == "failed"
    assert service.scheduler.graph_store.get_node("n_agent_failed").error_code == "SCHEDULER_AGENT_FAILED"
    assert service.scheduler.graph_store.get_graph("g_agent_failed").status == "failed"
    assert any(event.get("event_type") == "scheduler.agent.failed" for event in sink.recent(limit=50))
    service.stop()


def test_scheduler_crash_marks_unfinished_dag_failed():
    sink = InMemoryKernelEventSink()
    service, agent = _service_with_ready_graph("agent_crashed", sink=sink)

    response = service.crash_agent(agent.agent_id, reason="boom", error_code="APP_EXCEPTION")

    assert response.success is True
    assert service.scheduler.graph_store.get_node("n_agent_crashed").status == "failed"
    assert service.scheduler.graph_store.get_node("n_agent_crashed").error_code == "SCHEDULER_AGENT_CRASHED"
    assert service.scheduler.graph_store.get_graph("g_agent_crashed").status == "failed"
    assert any(
        event.get("event_type") == "scheduler.node.failed"
        and event.get("metadata", {}).get("lifecycle_event") == "crashed"
        for event in sink.recent(limit=50)
    )
    service.stop()


def test_scheduler_reap_preserves_terminal_graph_state_and_audits_reap():
    sink = InMemoryKernelEventSink()
    service, agent = _service_with_ready_graph("agent_reaped", sink=sink)
    service.exit_agent(agent.agent_id, reason="app_completed")

    response = service.reap_agent(agent.agent_id, reason="cleanup_done")

    assert response.success is True
    assert service.scheduler.graph_store.get_node("n_agent_reaped").status == "cancelled"
    assert service.scheduler.graph_store.get_graph("g_agent_reaped").status == "cancelled"
    assert any(event.get("event_type") == "scheduler.agent.reaped" for event in sink.recent(limit=80))
    service.stop()


def test_scheduler_reap_marks_leftover_nonterminal_nodes_stale():
    sink = InMemoryKernelEventSink()
    service, agent = _service_with_ready_graph("agent_reap_leftover", sink=sink)

    service.scheduler.on_agent_terminal(agent.agent_id, event_type="reaped", reason="cleanup_done")

    assert service.scheduler.graph_store.get_node("n_agent_reap_leftover").status == "stale"
    assert service.scheduler.graph_store.get_node("n_agent_reap_leftover").error_code == "SCHEDULER_AGENT_REAPED"
    assert service.scheduler.graph_store.get_graph("g_agent_reap_leftover").status == "failed"
    service.stop()


def test_scheduler_terminal_marks_dag_failed_when_resource_release_fails():
    class FailingReleaseDevice:
        def acquire(self, resource, owner, reason=""):
            return {"success": True, "lease": {"lease_id": f"lease_{resource}", "owner": owner}}

        def release(self, resource, owner):
            return {"success": False, "error_code": "DEVICE_RELEASE_FAILED", "resource": resource, "owner": owner}

    sink = InMemoryKernelEventSink()
    service, agent = _service_with_ready_graph("agent_release_failure", sink=sink)
    scheduler = service.scheduler
    scheduler.resource_arbiter.device_arbiter = FailingReleaseDevice()
    node = scheduler.graph_store.get_node("n_agent_release_failure")
    node.resources = [ResourceRequest("base", mode="exclusive", lease_ttl_ns=100_000_000_000)]
    lease_result = scheduler.resource_arbiter.try_acquire(node, at_ns=1)
    scheduler.graph_store.mark_status(node.node_id, "running")

    scheduler.on_agent_terminal(agent.agent_id, event_type="killed", reason="operator_kill")
    handle = service.agent_resources.get(lease_result.leases[0].agent_resource_handle_id)

    assert lease_result.success is True
    assert scheduler.graph_store.get_node(node.node_id).status == "failed"
    assert scheduler.graph_store.get_node(node.node_id).error_code == "SCHEDULER_RESOURCE_RELEASE_FAILED"
    assert scheduler.graph_store.get_graph("g_agent_release_failure").status == "failed"
    assert scheduler.resource_arbiter.snapshot()["leases"][lease_result.leases[0].lease_id]["status"] == "acquired"
    assert handle is not None
    assert handle.state == AgentResourceState.RELEASE_FAILED
    assert handle.release_error_code == "SCHEDULER_RESOURCE_RELEASE_FAILED"
    assert any(event.get("event_type") == "scheduler.agent.resource_release_failed" for event in sink.recent(limit=80))
    assert any(event.get("event_type") == "scheduler.resource.lease_release_failed" for event in sink.recent(limit=80))
    service.stop()


def _service_with_ready_graph(agent_id: str, *, sink: InMemoryKernelEventSink):
    service = KernelService(config=Config(), event_sink=sink)
    agent = service.create_agent(app_id="app", session_id="sess", agent_id=agent_id)
    service.start_agent(agent.agent_id)
    node = TaskNode.create(
        node_id=f"n_{agent_id}",
        task_graph_id=f"g_{agent_id}",
        user_goal_id="goal",
        agent_id=agent.agent_id,
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id=f"g_{agent_id}",
        user_goal_id="goal",
        root_goal="report",
        agent_id=agent.agent_id,
        app_id="app",
        session_id="sess",
        nodes={node.node_id: node},
    )
    response = service.scheduler.submit_graph(graph)
    assert response.success is True
    assert service.scheduler.graph_store.get_node(node.node_id).status == "ready"
    return service, agent
