from __future__ import annotations

from agentic_os.kernel.scheduler import PriorityScorer, QueryType, TaskGraph, TaskNode, TypedEdge, compute_critical_path_rank


def test_critical_path_and_priority_scoring():
    a = TaskNode.create(
        node_id="a",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        estimated_runtime_ns=5,
    )
    b = TaskNode.create(
        node_id="b",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        estimated_runtime_ns=7,
        opportunistic=True,
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"a": a, "b": b},
        edges=[TypedEdge("e", "a", "b")],
    )

    ranks = compute_critical_path_rank(graph)
    key = PriorityScorer().score(b, b.created_ns + 2_000_000_000)

    assert ranks["a"] == 12
    assert ranks["b"] == 7
    assert key.opportunity_rank == 10
