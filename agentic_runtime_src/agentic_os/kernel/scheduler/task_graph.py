from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call.models import monotonic_id

from .models import CoverageRequirement, EdgeType, FusionPolicy, RouteIntent, TaskGraphStatus, now_ns
from .task_node import TaskNode


@dataclass(frozen=True)
class TypedEdge:
    edge_id: str
    source_id: str
    target_id: str
    edge_type: str = EdgeType.PRECEDENCE
    fact_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TypedEdge":
        return cls(
            edge_id=str(data.get("edge_id") or monotonic_id("edge")),
            source_id=str(data.get("source_id") or data.get("source") or ""),
            target_id=str(data.get("target_id") or data.get("target") or ""),
            edge_type=str(data.get("edge_type") or EdgeType.PRECEDENCE),
            fact_key=str(data.get("fact_key") or ""),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskGraph:
    task_graph_id: str
    user_goal_id: str
    agent_id: str
    app_id: str
    session_id: str
    root_goal: str
    nodes: dict[str, TaskNode] = field(default_factory=dict)
    edges: list[TypedEdge] = field(default_factory=list)
    priority: int = 0
    deadline_ns: int | None = None
    max_concurrency: int = 1
    route_intent: RouteIntent | None = None
    coverage_requirements: list[CoverageRequirement] = field(default_factory=list)
    parent_goal_ids: list[str] = field(default_factory=list)
    merged_goal_ids: list[str] = field(default_factory=list)
    fusion_policy: FusionPolicy = field(default_factory=FusionPolicy)
    planner_call_syscall_id: str = ""
    planner_model: str = ""
    planner_schema_id: str = "task_graph.schema.json"
    validated_schema_version: str = ""
    status: str = TaskGraphStatus.CREATED
    created_ns: int = field(default_factory=now_ns)
    updated_ns: int = field(default_factory=now_ns)

    @classmethod
    def create(
        cls,
        *,
        root_goal: str,
        agent_id: str,
        app_id: str,
        session_id: str,
        user_goal_id: str = "",
        task_graph_id: str = "",
        **kwargs: Any,
    ) -> "TaskGraph":
        graph_id = task_graph_id or monotonic_id("graph")
        graph = cls(
            task_graph_id=graph_id,
            user_goal_id=user_goal_id or monotonic_id("goal"),
            agent_id=agent_id,
            app_id=app_id,
            session_id=session_id,
            root_goal=root_goal,
            **kwargs,
        )
        graph.attach_dependencies()
        return graph

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskGraph":
        graph_id = str(data.get("task_graph_id") or data.get("id") or monotonic_id("graph"))
        user_goal_id = str(data.get("user_goal_id") or monotonic_id("goal"))
        nodes_payload = data.get("nodes") or {}
        if isinstance(nodes_payload, list):
            node_items = [TaskNode.from_dict({**node, "task_graph_id": node.get("task_graph_id") or graph_id, "user_goal_id": node.get("user_goal_id") or user_goal_id}) for node in nodes_payload]
            nodes = {node.node_id: node for node in node_items}
        else:
            nodes = {
                str(node_id): TaskNode.from_dict(
                    {
                        **dict(node),
                        "node_id": str(node.get("node_id") or node_id),
                        "task_graph_id": str(node.get("task_graph_id") or graph_id),
                        "user_goal_id": str(node.get("user_goal_id") or user_goal_id),
                    }
                )
                for node_id, node in dict(nodes_payload).items()
            }
        edges = [edge if isinstance(edge, TypedEdge) else TypedEdge.from_dict(edge) for edge in list(data.get("edges") or [])]
        _attach_dependencies(nodes, edges)
        return cls(
            task_graph_id=graph_id,
            user_goal_id=user_goal_id,
            agent_id=str(data.get("agent_id") or ""),
            app_id=str(data.get("app_id") or ""),
            session_id=str(data.get("session_id") or ""),
            root_goal=str(data.get("root_goal") or ""),
            nodes=nodes,
            edges=edges,
            priority=int(data.get("priority", 0)),
            deadline_ns=data.get("deadline_ns"),
            max_concurrency=int(data.get("max_concurrency", 1)),
            route_intent=RouteIntent.from_dict(data.get("route_intent")),
            coverage_requirements=[CoverageRequirement.from_dict(item) for item in list(data.get("coverage_requirements") or [])],
            parent_goal_ids=list(data.get("parent_goal_ids") or []),
            merged_goal_ids=list(data.get("merged_goal_ids") or []),
            fusion_policy=FusionPolicy.from_dict(data.get("fusion_policy")),
            planner_call_syscall_id=str(data.get("planner_call_syscall_id") or ""),
            planner_model=str(data.get("planner_model") or ""),
            planner_schema_id=str(data.get("planner_schema_id") or "task_graph.schema.json"),
            validated_schema_version=str(data.get("validated_schema_version") or ""),
            status=str(data.get("status") or TaskGraphStatus.CREATED),
            created_ns=int(data.get("created_ns", now_ns())),
            updated_ns=int(data.get("updated_ns", now_ns())),
        )

    def precedence_edges(self) -> dict[str, set[str]]:
        edges: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        for edge in self.edges:
            if edge.edge_type == EdgeType.PRECEDENCE:
                edges.setdefault(edge.source_id, set()).add(edge.target_id)
        return edges

    def reverse_precedence_edges(self) -> dict[str, set[str]]:
        reverse: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        for source_id, targets in self.precedence_edges().items():
            for target_id in targets:
                reverse.setdefault(target_id, set()).add(source_id)
        return reverse

    def successors(self, node_id: str) -> set[str]:
        return set(self.precedence_edges().get(node_id, set()))

    def attach_dependencies(self) -> "TaskGraph":
        _attach_dependencies(self.nodes, self.edges)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_graph_id": self.task_graph_id,
            "user_goal_id": self.user_goal_id,
            "agent_id": self.agent_id,
            "app_id": self.app_id,
            "session_id": self.session_id,
            "root_goal": self.root_goal,
            "nodes": {node_id: node.to_dict() for node_id, node in sorted(self.nodes.items())},
            "edges": [edge.to_dict() for edge in self.edges],
            "priority": self.priority,
            "deadline_ns": self.deadline_ns,
            "max_concurrency": self.max_concurrency,
            "route_intent": self.route_intent.to_dict() if self.route_intent else None,
            "coverage_requirements": [item.to_dict() for item in self.coverage_requirements],
            "parent_goal_ids": list(self.parent_goal_ids),
            "merged_goal_ids": list(self.merged_goal_ids),
            "fusion_policy": self.fusion_policy.to_dict(),
            "planner_call_syscall_id": self.planner_call_syscall_id,
            "planner_model": self.planner_model,
            "planner_schema_id": self.planner_schema_id,
            "validated_schema_version": self.validated_schema_version,
            "status": self.status,
            "created_ns": self.created_ns,
            "updated_ns": self.updated_ns,
        }


def _attach_dependencies(nodes: dict[str, TaskNode], edges: list[TypedEdge]) -> None:
    for node in nodes.values():
        node.dependencies.clear()
        node.dependents.clear()
    for edge in edges:
        if edge.edge_type != EdgeType.PRECEDENCE:
            continue
        cross_graph_dependency = bool(edge.metadata.get("cross_graph_dependency"))
        if edge.target_id in nodes and (edge.source_id in nodes or cross_graph_dependency):
            nodes[edge.target_id].dependencies.add(edge.source_id)
        if edge.source_id in nodes and edge.target_id in nodes:
            nodes[edge.source_id].dependents.add(edge.target_id)
