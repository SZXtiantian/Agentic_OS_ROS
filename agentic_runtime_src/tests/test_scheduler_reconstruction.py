from __future__ import annotations

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.scheduler import EdgeType, EnvironmentAwareDAGScheduler, QueryType, SchedulerAudit, TaskGraph, TaskGraphStore, TaskNode, TypedEdge
from agentic_os.kernel.scheduler.environment import EnvironmentFact, EnvironmentStore
from agentic_os.kernel.scheduler.opportunity import OpportunityIndex
from agentic_os.kernel.scheduler.preconditions import Precondition
from agentic_os.kernel.scheduler.reconstruction import DynamicGraphEvent, FactReusePlanner, OnlineGraphReconstructor


def test_dynamic_graph_event_reassigns_deadline_for_impacted_nodes():
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="perception.observe",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["obstacle"],
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node},
    )

    result = OnlineGraphReconstructor().stage_mutation(
        graph,
        DynamicGraphEvent.create("fact_changed", fact_key="obstacle", deadline_ns=1_000_000_000),
    )

    assert result["success"] is True
    assert result["impacted_nodes"] == ["n"]
    assert result["deadline_reassignment"]["n"] is not None


def test_dynamic_graph_event_rejects_deadline_budget_below_impacted_critical_path():
    sink = InMemoryKernelEventSink()
    reconstructor = OnlineGraphReconstructor(audit=SchedulerAudit(event_sink=sink))
    observe = TaskNode.create(
        node_id="observe",
        task_graph_id="g_deadline_budget",
        user_goal_id="goal_deadline_budget",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="perception.observe",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["obstacle"],
        estimated_runtime_ns=1_000_000_000,
    )
    avoid = TaskNode.create(
        node_id="avoid",
        task_graph_id="g_deadline_budget",
        user_goal_id="goal_deadline_budget",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="navigation.avoid_obstacle",
        query_type=QueryType.ROBOT_CAPABILITY,
        estimated_runtime_ns=1_000_000_000,
    )
    graph = TaskGraph.create(
        task_graph_id="g_deadline_budget",
        user_goal_id="goal_deadline_budget",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"observe": observe, "avoid": avoid},
        edges=[TypedEdge("observe_then_avoid", "observe", "avoid", EdgeType.PRECEDENCE)],
    )

    staged = reconstructor.stage_graph_mutation(
        graph,
        DynamicGraphEvent.create("fact_changed", fact_key="obstacle", deadline_ns=1_500_000_000),
    )

    result = staged.to_dict()
    assert staged.success is False
    assert result["error_code"] == "SCHEDULER_DEADLINE_UNSATISFIABLE"
    assert result["deadline_budget_ns"] == 1_500_000_000
    assert result["required_runtime_budget_ns"] == 2_000_000_000
    assert result["deadline_slack_ns"] == -500_000_000
    assert result["impacted_nodes"] == ["avoid", "observe"]
    assert any(
        event["event_type"] == "scheduler.reconstruction.staged"
        and event["metadata"]["error_code"] == "SCHEDULER_DEADLINE_UNSATISFIABLE"
        and event["metadata"]["deadline_slack_ns"] == -500_000_000
        for event in sink.recent(limit=20)
    )


def test_staged_graph_mutation_commits_revision_and_dirty_refresh():
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="perception.observe",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["obstacle"],
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node},
    )
    store = TaskGraphStore()
    store.add_graph(graph)
    reconstructor = OnlineGraphReconstructor()
    staged = reconstructor.stage_graph_mutation(
        graph,
        DynamicGraphEvent.create("fact_changed", fact_key="obstacle", deadline_ns=1_000_000_000),
    )

    result = reconstructor.commit_staged_mutation(store, staged)

    assert result["success"] is True
    assert result["dirty_nodes_refreshed"] == ["n"]
    assert store.dirty_node_ids() == set()
    assert store.revision >= 2


def test_dynamic_graph_event_marks_transitive_dependents_impacted():
    observe = TaskNode.create(
        node_id="observe",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="perception.observe",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["obstacle"],
    )
    avoid = TaskNode.create(
        node_id="avoid",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="navigation.avoid_obstacle",
        query_type=QueryType.ROBOT_CAPABILITY,
    )
    report = TaskNode.create(
        node_id="report",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"observe": observe, "avoid": avoid, "report": report},
        edges=[
            TypedEdge("e1", "observe", "avoid", EdgeType.PRECEDENCE),
            TypedEdge("e2", "avoid", "report", EdgeType.PRECEDENCE),
        ],
    )

    result = OnlineGraphReconstructor().stage_mutation(
        graph,
        DynamicGraphEvent.create("fact_changed", fact_key="obstacle", deadline_ns=3_000_000_000),
    )

    assert result["success"] is True
    assert result["impacted_nodes"] == ["avoid", "observe", "report"]


def test_staged_graph_mutation_rejects_stale_base_revision():
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="perception.observe",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["obstacle"],
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node},
    )
    other = TaskNode.create(
        node_id="other",
        task_graph_id="other_graph",
        user_goal_id="other_goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    other_graph = TaskGraph.create(
        task_graph_id="other_graph",
        user_goal_id="other_goal",
        root_goal="other",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"other": other},
    )
    store = TaskGraphStore()
    store.add_graph(graph)
    base_revision = store.revision
    reconstructor = OnlineGraphReconstructor()
    staged = reconstructor.stage_graph_mutation(
        graph,
        DynamicGraphEvent.create("fact_changed", fact_key="obstacle", deadline_ns=1_000_000_000),
        base_revision=base_revision,
    )
    store.add_graph(other_graph)

    result = reconstructor.commit_staged_mutation(store, staged)

    assert result["success"] is False
    assert result["error_code"] == "SCHEDULER_GRAPH_REVISION_CONFLICT"
    assert result["base_revision"] == base_revision
    assert result["current_revision"] == store.revision
    assert store.get_graph("g").nodes["n"].deadline_ns is None


def test_dynamic_graph_event_impacts_precondition_fact_dependencies_and_refreshes_index():
    wait_for_door = TaskNode.create(
        node_id="wait_for_door",
        task_graph_id="g_precondition",
        user_goal_id="goal_precondition",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        preconditions=[Precondition("door_open", operator="eq", expected=True)],
    )
    enter_room = TaskNode.create(
        node_id="enter_room",
        task_graph_id="g_precondition",
        user_goal_id="goal_precondition",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
    )
    graph = TaskGraph.create(
        task_graph_id="g_precondition",
        user_goal_id="goal_precondition",
        root_goal="inspect room",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"wait_for_door": wait_for_door, "enter_room": enter_room},
        edges=[TypedEdge("door_then_enter", "wait_for_door", "enter_room", EdgeType.PRECEDENCE)],
    )
    store = TaskGraphStore()
    store.add_graph(graph)

    staged = OnlineGraphReconstructor().stage_graph_mutation(
        graph,
        DynamicGraphEvent.create("fact_changed", fact_key="door_open", deadline_ns=2_000_000_000),
        base_revision=store.revision,
    )
    result = OnlineGraphReconstructor().commit_staged_mutation(store, staged)

    assert staged.success is True
    assert staged.impacted_nodes == {"wait_for_door", "enter_room"}
    assert result["success"] is True
    assert result["dirty_nodes_refreshed"] == ["enter_room", "wait_for_door"]
    assert store.global_dag.node_index_by_fact["door_open"] == {"wait_for_door"}


def test_fact_reuse_planner_considers_precondition_fact_dependencies():
    graph = TaskGraph.create(
        task_graph_id="g_reuse_precondition",
        user_goal_id="goal_reuse_precondition",
        root_goal="inspect room",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={
            "wait_for_door": TaskNode.create(
                node_id="wait_for_door",
                task_graph_id="g_reuse_precondition",
                user_goal_id="goal_reuse_precondition",
                agent_id="agent",
                agent_name="app",
                app_id="app",
                session_id="sess",
                capability="robot.inspect_area",
                query_type=QueryType.ROBOT_CAPABILITY,
                preconditions=[Precondition("door_open", operator="eq", expected=True)],
            )
        },
    )
    environment = EnvironmentStore()
    environment.put(
        EnvironmentFact.create(
            key="door_open",
            value=True,
            source_node_id="detect_door",
            source_capability="perception.observe",
            source_syscall_id="ksc_real",
            source_audit_id="audit_real",
            source_result={"door_open": True},
            ttl_ns=30_000_000_000,
            confidence=0.99,
            world_epoch=environment.world_epoch,
            schema_id="",
            real_dependency="ros_bridge",
        )
    )

    assert FactReusePlanner().reusable_fact_keys(graph, environment) == ["door_open"]


def test_reconstruction_commit_and_rejection_are_audited():
    sink = InMemoryKernelEventSink()
    reconstructor = OnlineGraphReconstructor(audit=SchedulerAudit(event_sink=sink))
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g_audit",
        user_goal_id="goal_audit",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="perception.observe",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["obstacle"],
    )
    graph = TaskGraph.create(
        task_graph_id="g_audit",
        user_goal_id="goal_audit",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node},
    )
    store = TaskGraphStore()
    store.add_graph(graph)
    staged = reconstructor.stage_graph_mutation(
        graph,
        DynamicGraphEvent.create("fact_changed", fact_key="obstacle", deadline_ns=1_000_000_000),
        base_revision=store.revision,
    )

    result = reconstructor.commit_staged_mutation(store, staged)
    events = sink.recent(limit=20)

    assert result["success"] is True
    assert any(
        event["event_type"] == "scheduler.reconstruction.staged"
        and event["metadata"]["task_graph_id"] == "g_audit"
        and event["metadata"]["success"] is True
        for event in events
    )
    assert any(
        event["event_type"] == "scheduler.reconstruction.committed"
        and event["metadata"]["task_graph_id"] == "g_audit"
        and event["metadata"]["dirty_nodes_refreshed"] == ["n"]
        for event in events
    )

    stale = reconstructor.stage_graph_mutation(
        store.get_graph("g_audit"),
        DynamicGraphEvent.create("fact_changed", fact_key="obstacle", deadline_ns=1_000_000_000),
        base_revision=store.revision,
    )
    other = TaskNode.create(
        node_id="other",
        task_graph_id="g_other",
        user_goal_id="goal_other",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    store.add_graph(
        TaskGraph.create(
            task_graph_id="g_other",
            user_goal_id="goal_other",
            root_goal="other",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            nodes={"other": other},
        )
    )

    rejected = reconstructor.commit_staged_mutation(store, stale)
    events = sink.recent(limit=40)

    assert rejected["success"] is False
    assert rejected["error_code"] == "SCHEDULER_GRAPH_REVISION_CONFLICT"
    assert any(
        event["event_type"] == "scheduler.reconstruction.rejected"
        and event["metadata"]["error_code"] == "SCHEDULER_GRAPH_REVISION_CONFLICT"
        and event["metadata"]["task_graph_id"] == "g_audit"
        for event in events
    )


def test_scheduler_service_applies_dynamic_graph_event_to_live_graph_store_and_refreshes_ready_queue():
    class RecordingOpportunityIndex(OpportunityIndex):
        def __init__(self):
            super().__init__()
            self.rebuilt_graph_ids = []

        def rebuild_from_graph(self, graph):
            self.rebuilt_graph_ids.append(graph.task_graph_id)
            super().rebuild_from_graph(graph)

    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, event_sink=sink)
    scheduler.opportunity_index = RecordingOpportunityIndex()
    node = TaskNode.create(
        node_id="observe_obstacle",
        task_graph_id="g_service_reconstruct",
        user_goal_id="goal_service_reconstruct",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["obstacle"],
        workspace_zone="zone_a",
        route_segment_id="route_a",
    )
    graph = TaskGraph.create(
        task_graph_id="g_service_reconstruct",
        user_goal_id="goal_service_reconstruct",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={node.node_id: node},
    )
    assert scheduler.submit_graph(graph).success is True
    base_revision = scheduler.graph_store.revision

    response = scheduler.apply_dynamic_graph_event(
        {"event_type": "fact_changed", "fact_key": "obstacle", "deadline_ns": 1_000_000_000},
        task_graph_id="g_service_reconstruct",
    )
    stored = scheduler.graph_store.get_node("observe_obstacle")
    events = sink.recent(limit=80)

    assert response.success is True
    assert response.data["committed_graphs"] == ["g_service_reconstruct"]
    assert response.data["results"][0]["dirty_nodes_refreshed"] == ["observe_obstacle"]
    assert stored.deadline_ns is not None
    assert scheduler.graph_store.revision > base_revision
    assert any(item["node_id"] == "observe_obstacle" for item in scheduler.ready_queue.snapshot())
    assert scheduler.opportunity_index.rebuilt_graph_ids == ["g_service_reconstruct", "g_service_reconstruct"]
    assert len(scheduler.opportunity_index.snapshot()) == 1
    assert any(
        event["event_type"] == "scheduler.reconstruction.committed"
        and event["metadata"]["task_graph_id"] == "g_service_reconstruct"
        and event["metadata"]["dirty_nodes_refreshed"] == ["observe_obstacle"]
        for event in events
    )


def test_scheduler_dynamic_graph_event_surfaces_reusable_fact_keys_from_environment_store():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, event_sink=sink)
    graph = TaskGraph.create(
        task_graph_id="g_service_reuse",
        user_goal_id="goal_service_reuse",
        root_goal="inspect room",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={
            "wait_for_door": TaskNode.create(
                node_id="wait_for_door",
                task_graph_id="g_service_reuse",
                user_goal_id="goal_service_reuse",
                agent_id="agent",
                agent_name="app",
                app_id="app",
                session_id="sess",
                capability="robot.inspect_area",
                query_type=QueryType.ROBOT_CAPABILITY,
                preconditions=[Precondition("door_open", operator="eq", expected=True)],
            )
        },
    )
    scheduler.environment_store.put(
        EnvironmentFact.create(
            key="door_open",
            value=True,
            source_node_id="detect_door",
            source_capability="perception.observe",
            source_syscall_id="ksc_real",
            source_audit_id="audit_real",
            source_result={"door_open": True},
            ttl_ns=30_000_000_000,
            confidence=0.99,
            world_epoch=scheduler.environment_store.world_epoch,
            schema_id="",
            real_dependency="ros_bridge",
        )
    )
    assert scheduler.submit_graph(graph).success is True

    response = scheduler.apply_dynamic_graph_event(
        DynamicGraphEvent.create("fact_changed", fact_key="door_open", deadline_ns=1_000_000_000),
        task_graph_id="g_service_reuse",
    )
    events = sink.recent(limit=80)

    assert response.success is True
    assert response.data["results"][0]["reusable_fact_keys"] == ["door_open"]
    assert any(
        event["event_type"] == "scheduler.reconstruction.staged"
        and event["metadata"]["reusable_fact_keys"] == ["door_open"]
        for event in events
    )


def test_scheduler_dynamic_graph_event_rejects_invalid_mapping_with_stable_error():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, event_sink=sink)

    response = scheduler.apply_dynamic_graph_event({"fact_key": "door_open"})

    assert response.success is False
    assert response.error_code == "SCHEDULER_DYNAMIC_EVENT_INVALID"
    assert response.metadata["reason"] == "event_type required"
    assert any(
        event["event_type"] == "scheduler.reconstruction.rejected"
        and event["metadata"]["error_code"] == "SCHEDULER_DYNAMIC_EVENT_INVALID"
        for event in sink.recent(limit=20)
    )
