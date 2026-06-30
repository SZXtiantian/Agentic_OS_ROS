from __future__ import annotations

from collections import deque

from .errors import SchedulerError
from .task_graph import TaskGraph

DEFAULT_NODE_RUNTIME_NS = 1_000_000_000


def topological_sort(graph: TaskGraph) -> list[str]:
    edges: dict[str, set[str]] = {node_id: set() for node_id in graph.nodes}
    indegree = {node_id: 0 for node_id in graph.nodes}
    for edge in graph.edges:
        if edge.edge_type != "precedence":
            continue
        source_id = edge.source_id
        target_id = edge.target_id
        cross_graph_dependency = bool(edge.metadata.get("cross_graph_dependency"))
        if source_id not in indegree or target_id not in indegree:
            if cross_graph_dependency:
                continue
            missing_node_id = source_id if source_id not in indegree else target_id
            raise SchedulerError("SCHEDULER_GRAPH_SCHEMA_INVALID", metadata={"missing_node_id": missing_node_id})
        edges.setdefault(source_id, set()).add(target_id)
        indegree[target_id] += 1

    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while queue:
        node_id = queue.popleft()
        ordered.append(node_id)
        for target_id in sorted(edges.get(node_id, set())):
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)
    if len(ordered) != len(graph.nodes):
        raise SchedulerError("SCHEDULER_DAG_CYCLE", metadata={"task_graph_id": graph.task_graph_id})
    return ordered


def validate_acyclic(graph: TaskGraph) -> None:
    topological_sort(graph)


def compute_critical_path_rank(graph: TaskGraph) -> dict[str, int]:
    ordered = topological_sort(graph)
    rank: dict[str, int] = {}
    edges = _local_precedence_edges(graph)
    for node_id in reversed(ordered):
        node = graph.nodes[node_id]
        successors = edges.get(node_id, set())
        own_cost = int(node.estimated_runtime_ns or DEFAULT_NODE_RUNTIME_NS)
        rank[node_id] = own_cost if not successors else own_cost + max(rank[successor] for successor in successors)
    for node_id, value in rank.items():
        graph.nodes[node_id].critical_path_rank = value
    return rank


def _local_precedence_edges(graph: TaskGraph) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {node_id: set() for node_id in graph.nodes}
    for edge in graph.edges:
        if edge.edge_type != "precedence":
            continue
        if edge.source_id in graph.nodes and edge.target_id in graph.nodes:
            edges.setdefault(edge.source_id, set()).add(edge.target_id)
    return edges
