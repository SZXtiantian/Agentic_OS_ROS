from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import TaskNodeStatus
from .task_graph import TaskGraph
from .task_node import TaskNode, fact_keys_for_node


@dataclass
class GlobalGoalDAG:
    revision: int = 0
    nodes: dict[str, TaskNode] = field(default_factory=dict)
    graphs: dict[str, TaskGraph] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=dict)
    reverse_edges: dict[str, set[str]] = field(default_factory=dict)
    ready_set: set[str] = field(default_factory=set)
    running_set: set[str] = field(default_factory=set)
    blocked_set: set[str] = field(default_factory=set)
    completed_set: set[str] = field(default_factory=set)
    failed_set: set[str] = field(default_factory=set)
    node_index_by_agent: dict[str, set[str]] = field(default_factory=dict)
    node_index_by_resource: dict[str, set[str]] = field(default_factory=dict)
    node_index_by_capability: dict[str, set[str]] = field(default_factory=dict)
    node_index_by_workspace_zone: dict[str, set[str]] = field(default_factory=dict)
    node_index_by_route_segment: dict[str, set[str]] = field(default_factory=dict)
    node_index_by_fact: dict[str, set[str]] = field(default_factory=dict)

    def rebuild_indexes(self) -> None:
        self.edges = {node_id: set() for node_id in self.nodes}
        self.reverse_edges = {node_id: set() for node_id in self.nodes}
        for graph in self.graphs.values():
            for source_id, targets in graph.precedence_edges().items():
                self.edges.setdefault(source_id, set()).update(targets)
                for target_id in targets:
                    self.reverse_edges.setdefault(target_id, set()).add(source_id)

        self.ready_set = {node.node_id for node in self.nodes.values() if node.status == TaskNodeStatus.READY}
        self.running_set = {node.node_id for node in self.nodes.values() if node.status == TaskNodeStatus.RUNNING}
        self.blocked_set = {node.node_id for node in self.nodes.values() if node.status == TaskNodeStatus.BLOCKED}
        self.completed_set = {node.node_id for node in self.nodes.values() if node.status == TaskNodeStatus.COMPLETED}
        self.failed_set = {node.node_id for node in self.nodes.values() if node.status == TaskNodeStatus.FAILED}
        self.node_index_by_agent = _index(self.nodes.values(), lambda node: node.agent_id)
        self.node_index_by_capability = _index(self.nodes.values(), lambda node: node.capability)
        self.node_index_by_workspace_zone = _index(self.nodes.values(), lambda node: node.workspace_zone or "")
        self.node_index_by_route_segment = _index(self.nodes.values(), lambda node: node.route_segment_id or "")
        self.node_index_by_resource = {}
        self.node_index_by_fact = {}
        for node in self.nodes.values():
            for request in node.resources:
                self.node_index_by_resource.setdefault(request.resource_id, set()).add(node.node_id)
            for fact_key in fact_keys_for_node(node):
                self.node_index_by_fact.setdefault(fact_key, set()).add(node.node_id)

    def counts(self) -> dict[str, int]:
        by_status: dict[str, int] = {}
        for node in self.nodes.values():
            by_status[node.status] = by_status.get(node.status, 0) + 1
        return by_status

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "graphs": {graph_id: graph.to_dict() for graph_id, graph in sorted(self.graphs.items())},
            "nodes": {node_id: node.to_dict() for node_id, node in sorted(self.nodes.items())},
            "edges": {node_id: sorted(targets) for node_id, targets in sorted(self.edges.items())},
            "reverse_edges": {node_id: sorted(sources) for node_id, sources in sorted(self.reverse_edges.items())},
            "nodes_by_status": self.counts(),
        }


def _index(nodes, key_fn) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for node in nodes:
        key = key_fn(node)
        if key:
            index.setdefault(str(key), set()).add(node.node_id)
    return index
