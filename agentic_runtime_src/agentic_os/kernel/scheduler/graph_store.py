from __future__ import annotations

from copy import deepcopy
from threading import RLock

from .critical_path import compute_critical_path_rank, validate_acyclic
from .global_dag import GlobalGoalDAG
from .models import TaskGraphStatus, TaskNodeStatus, now_ns
from .task_graph import TaskGraph
from .task_node import TaskNode


class TaskGraphStore:
    def __init__(self) -> None:
        self.global_dag = GlobalGoalDAG()
        self._lock = RLock()
        self._dirty_node_ids: set[str] = set()

    @property
    def revision(self) -> int:
        return self.global_dag.revision

    def add_graph(self, graph: TaskGraph) -> None:
        graph.attach_dependencies()
        validate_acyclic(graph)
        compute_critical_path_rank(graph)
        with self._lock:
            graph.status = TaskGraphStatus.ADMITTED
            graph.updated_ns = now_ns()
            self.global_dag.graphs[graph.task_graph_id] = graph
            for node in graph.nodes.values():
                if node.status == TaskNodeStatus.CREATED:
                    node.status = TaskNodeStatus.ADMITTED
                self.global_dag.nodes[node.node_id] = node
            self._bump()

    def get_node(self, node_id: str) -> TaskNode:
        return self.global_dag.nodes[node_id]

    def get_graph(self, task_graph_id: str) -> TaskGraph:
        return self.global_dag.graphs[task_graph_id]

    def waiting_nodes(self) -> list[TaskNode]:
        return [
            node
            for node in self.global_dag.nodes.values()
            if node.status in {TaskNodeStatus.ADMITTED, TaskNodeStatus.WAITING, TaskNodeStatus.BLOCKED}
        ]

    def dependencies_completed(self, node: TaskNode) -> bool:
        dependency_ids = set(node.dependencies)
        dependency_ids.update(self.global_dag.reverse_edges.get(node.node_id, set()))
        for dep in dependency_ids:
            dependency = self.global_dag.nodes.get(dep)
            if dependency is None or dependency.status != TaskNodeStatus.COMPLETED:
                return False
        return True

    def mark_status(self, node_id: str, status: str, *, error_code: str = "") -> TaskNode:
        with self._lock:
            node = self.global_dag.nodes[node_id]
            node.mark_status(status, error_code=error_code)
            graph = self.global_dag.graphs.get(node.task_graph_id)
            if graph is not None:
                self._refresh_graph_status(graph)
            self._bump()
            return node

    def nodes_for_agent(self, agent_id: str) -> list[TaskNode]:
        return [node for node in self.global_dag.nodes.values() if node.agent_id == agent_id]

    def snapshot_metadata(self) -> GlobalGoalDAG:
        with self._lock:
            return deepcopy(self.global_dag)

    def mark_dirty_nodes(self, node_ids: set[str] | list[str]) -> None:
        with self._lock:
            self._dirty_node_ids.update(str(node_id) for node_id in node_ids)

    def dirty_node_ids(self) -> set[str]:
        with self._lock:
            return set(self._dirty_node_ids)

    def apply_changed_nodes(self, node_ids: set[str] | list[str] | None = None) -> None:
        with self._lock:
            if node_ids is not None:
                self._dirty_node_ids.update(str(node_id) for node_id in node_ids)
            self._bump()
            self._dirty_node_ids.clear()

    def _bump(self) -> None:
        self.global_dag.revision += 1
        self.global_dag.rebuild_indexes()

    def _refresh_graph_status(self, graph: TaskGraph) -> None:
        statuses = {node.status for node in graph.nodes.values()}
        if statuses and statuses <= {TaskNodeStatus.COMPLETED}:
            graph.status = TaskGraphStatus.COMPLETED
            graph.updated_ns = now_ns()
            return
        if statuses & {TaskNodeStatus.FAILED, TaskNodeStatus.STALE}:
            graph.status = TaskGraphStatus.FAILED
            graph.updated_ns = now_ns()
            return
        if statuses & {TaskNodeStatus.CANCELLED, TaskNodeStatus.REJECTED}:
            graph.status = TaskGraphStatus.CANCELLED
            graph.updated_ns = now_ns()
            return
        if statuses & {TaskNodeStatus.SUSPENDED}:
            graph.status = TaskGraphStatus.PARTIALLY_SUSPENDED
            graph.updated_ns = now_ns()
            return
        if statuses & {TaskNodeStatus.LEASED, TaskNodeStatus.DISPATCHING, TaskNodeStatus.RUNNING, TaskNodeStatus.COMPLETED}:
            graph.status = TaskGraphStatus.RUNNING
            graph.updated_ns = now_ns()
