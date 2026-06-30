from __future__ import annotations

import pytest

from agentic_os.kernel.scheduler import QueryType, SchedulerError, TaskGraph, TaskNode, TypedEdge, topological_sort, validate_acyclic


def _node(node_id: str) -> TaskNode:
    return TaskNode.create(
        node_id=node_id,
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )


def test_topological_sort_and_cycle_detection():
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"a": _node("a"), "b": _node("b")},
        edges=[TypedEdge("e1", "a", "b")],
    )

    assert topological_sort(graph) == ["a", "b"]

    cyclic = TaskGraph.create(
        task_graph_id="g2",
        user_goal_id="goal",
        root_goal="cycle",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"a": _node("a"), "b": _node("b")},
        edges=[TypedEdge("e1", "a", "b"), TypedEdge("e2", "b", "a")],
    )
    with pytest.raises(SchedulerError, match="SCHEDULER_DAG_CYCLE"):
        validate_acyclic(cyclic)
