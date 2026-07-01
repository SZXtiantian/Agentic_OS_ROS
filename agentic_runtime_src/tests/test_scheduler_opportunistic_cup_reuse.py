from __future__ import annotations

from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, QueryType, TaskGraph, TaskNode
from agentic_os.kernel.scheduler.environment import EnvironmentFact
from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.capability import CapabilityRegistry


def test_cup_reuse_does_not_skip_real_pick_verify_deliver_nodes():
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, event_sink=InMemoryKernelEventSink())
    inspection_detect = TaskNode.create(
        node_id="inspection_detect",
        task_graph_id="inspection_graph",
        user_goal_id="goal_inspect",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="perception.detect_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        produces_facts=["cup_pose"],
        workspace_zone="table",
        route_segment_id="route_table",
    )
    inspection_graph = TaskGraph.create(
        task_graph_id="inspection_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"inspection_detect": inspection_detect},
    )
    assert scheduler.submit_graph(inspection_graph).success is True
    scheduler.environment_store.put(
        EnvironmentFact.create(
            key="cup_pose",
            value={"x": 1.0, "workspace_zone": "table"},
            source_node_id="inspection_detect",
            source_capability="perception.detect_cup",
            source_syscall_id="ksc_real",
            source_audit_id="audit_real",
            source_result={"cup_pose": {"x": 1.0}},
            ttl_ns=30_000_000_000,
            confidence=0.94,
            world_epoch=0,
            schema_id="",
            real_dependency="ros_bridge",
        )
    )
    nodes = {
        "pick_cup": TaskNode.create(
            node_id="pick_cup",
            task_graph_id="cup_graph",
            user_goal_id="goal_cup",
            agent_id="agent",
            agent_name="app",
            app_id="app",
            session_id="sess",
            capability="manipulation.pick_cup",
            query_type=QueryType.ROBOT_CAPABILITY,
            consumes_facts=["cup_pose"],
            workspace_zone="table",
            route_segment_id="route_table",
        ),
        "verify_cup_held": TaskNode.create(
            node_id="verify_cup_held",
            task_graph_id="cup_graph",
            user_goal_id="goal_cup",
            agent_id="agent",
            agent_name="app",
            app_id="app",
            session_id="sess",
            capability="perception.verify_cup_held",
            query_type=QueryType.ROBOT_CAPABILITY,
            workspace_zone="table",
            route_segment_id="route_table",
        ),
        "deliver_cup": TaskNode.create(
            node_id="deliver_cup",
            task_graph_id="cup_graph",
            user_goal_id="goal_cup",
            agent_id="agent",
            agent_name="app",
            app_id="app",
            session_id="sess",
            capability="manipulation.deliver_cup",
            query_type=QueryType.ROBOT_CAPABILITY,
            workspace_zone="table",
            route_segment_id="route_table",
        ),
    }
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes=nodes,
    )

    response = scheduler.submit_graph(graph)

    assert response.success is True
    assert set(scheduler.graph_store.get_graph("cup_graph").nodes) == {"pick_cup", "verify_cup_held", "deliver_cup"}
    assert scheduler.fusion_engine.snapshot()[-1]["accepted"] is True


def test_missing_real_cup_capability_is_stable_unavailable(runtime_src):
    registry = CapabilityRegistry().load_skill_manifests(runtime_src / "system_skills")
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        event_sink=InMemoryKernelEventSink(),
        capability_registry=registry,
    )
    node = TaskNode.create(
        node_id="pick_cup",
        task_graph_id="cup_graph_missing",
        user_goal_id="goal_cup",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="manipulation.pick_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph_missing",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick_cup": node},
    )

    response = scheduler.submit_graph(graph)

    assert response.success is False
    assert response.error_code == "SCHEDULER_CAPABILITY_UNAVAILABLE"
