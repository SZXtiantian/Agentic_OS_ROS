from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call.models import monotonic_id

from .audit import SchedulerAudit
from .critical_path import DEFAULT_NODE_RUNTIME_NS, compute_critical_path_rank, topological_sort, validate_acyclic
from .environment import EnvironmentStore
from .models import now_ns
from .task_graph import TaskGraph
from .task_node import consumed_fact_keys_for_node, fact_keys_for_node


@dataclass
class StagedGraphMutation:
    success: bool
    event: DynamicGraphEvent
    graph: TaskGraph
    impacted_nodes: set[str]
    deadline_reassignment: dict[str, int | None]
    reusable_fact_keys: list[str] = field(default_factory=list)
    base_revision: int | None = None
    error_code: str = ""
    deadline_budget_ns: int | None = None
    required_runtime_budget_ns: int = 0
    deadline_slack_ns: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "error_code": self.error_code,
            "base_revision": self.base_revision,
            "deadline_budget_ns": self.deadline_budget_ns,
            "required_runtime_budget_ns": self.required_runtime_budget_ns,
            "deadline_slack_ns": self.deadline_slack_ns,
            "event": self.event.to_dict(),
            "impacted_nodes": sorted(self.impacted_nodes),
            "deadline_reassignment": dict(self.deadline_reassignment),
            "reusable_fact_keys": list(self.reusable_fact_keys),
            "graph": self.graph.to_dict(),
        }


@dataclass(frozen=True)
class DynamicGraphEvent:
    event_id: str
    event_type: str
    fact_key: str = ""
    node_id: str = ""
    deadline_ns: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, event_type: str, **kwargs: Any) -> "DynamicGraphEvent":
        return cls(event_id=monotonic_id("dge"), event_type=event_type, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DynamicGraphEvent":
        deadline = data.get("deadline_ns")
        return cls(
            event_id=str(data.get("event_id") or monotonic_id("dge")),
            event_type=str(data.get("event_type") or ""),
            fact_key=str(data.get("fact_key") or ""),
            node_id=str(data.get("node_id") or ""),
            deadline_ns=int(deadline) if deadline is not None else None,
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ImpactIndex:
    def impacted_nodes(self, graph: TaskGraph, event: DynamicGraphEvent) -> set[str]:
        seeds: set[str] = set()
        for node in graph.nodes.values():
            if event.fact_key and event.fact_key in fact_keys_for_node(node):
                seeds.add(node.node_id)
            if event.node_id and (node.node_id == event.node_id or event.node_id in node.dependencies):
                seeds.add(node.node_id)
        return self._with_transitive_successors(graph, seeds)

    def _with_transitive_successors(self, graph: TaskGraph, node_ids: set[str]) -> set[str]:
        impacted = set(node_ids)
        stack = list(node_ids)
        while stack:
            node_id = stack.pop()
            for successor_id in graph.successors(node_id):
                if successor_id not in impacted:
                    impacted.add(successor_id)
                    stack.append(successor_id)
        return impacted


class DeadlineBudgeter:
    def reassign(self, graph: TaskGraph, impacted_node_ids: set[str], *, event_deadline_ns: int | None = None) -> dict[str, int | None]:
        if event_deadline_ns is None:
            return {node_id: graph.nodes[node_id].deadline_ns for node_id in impacted_node_ids}
        ordered = [node_id for node_id in topological_sort(graph) if node_id in impacted_node_ids]
        reassigned: dict[str, int | None] = {}
        base = now_ns()
        elapsed = 0
        for node_id in ordered:
            elapsed += max(1, int(graph.nodes[node_id].estimated_runtime_ns or DEFAULT_NODE_RUNTIME_NS))
            graph.nodes[node_id].deadline_ns = base + min(int(event_deadline_ns), elapsed)
            reassigned[node_id] = graph.nodes[node_id].deadline_ns
        return reassigned

    def required_budget_ns(self, graph: TaskGraph, impacted_node_ids: set[str]) -> int:
        if not impacted_node_ids:
            return 0
        compute_critical_path_rank(graph)
        return max(int(graph.nodes[node_id].critical_path_rank or DEFAULT_NODE_RUNTIME_NS) for node_id in impacted_node_ids)


class FactReusePlanner:
    def reusable_fact_keys(self, graph: TaskGraph, environment: EnvironmentStore) -> list[str]:
        result: list[str] = []
        for node in graph.nodes.values():
            for fact_key in consumed_fact_keys_for_node(node):
                accepted, _flags = environment.validate_reuse(fact_key)
                if accepted:
                    result.append(fact_key)
        return sorted(set(result))


class CriticalDeadlineProtector:
    def validate(self, graph: TaskGraph) -> bool:
        compute_critical_path_rank(graph)
        current = now_ns()
        for node in graph.nodes.values():
            if node.deadline_ns is not None and node.deadline_ns < current:
                return False
        return True


class OnlineGraphReconstructor:
    def __init__(self, *, audit: SchedulerAudit | None = None) -> None:
        self.impact_index = ImpactIndex()
        self.deadline_budgeter = DeadlineBudgeter()
        self.fact_reuse_planner = FactReusePlanner()
        self.deadline_protector = CriticalDeadlineProtector()
        self.audit = audit or SchedulerAudit()

    def stage_mutation(
        self,
        graph: TaskGraph,
        event: DynamicGraphEvent,
        *,
        base_revision: int | None = None,
        environment: EnvironmentStore | None = None,
    ) -> dict[str, Any]:
        return self.stage_graph_mutation(graph, event, base_revision=base_revision, environment=environment).to_dict()

    def stage_graph_mutation(
        self,
        graph: TaskGraph,
        event: DynamicGraphEvent,
        *,
        base_revision: int | None = None,
        environment: EnvironmentStore | None = None,
    ) -> StagedGraphMutation:
        staging = deepcopy(graph)
        staging.attach_dependencies()
        impacted = self.impact_index.impacted_nodes(staging, event)
        validate_acyclic(staging)
        required_runtime_budget_ns = self.deadline_budgeter.required_budget_ns(staging, impacted)
        deadline_budget_ns = int(event.deadline_ns) if event.deadline_ns is not None else None
        deadline_slack_ns = None if deadline_budget_ns is None else deadline_budget_ns - required_runtime_budget_ns
        deadlines = self.deadline_budgeter.reassign(staging, impacted, event_deadline_ns=event.deadline_ns)
        reusable_fact_keys = self.fact_reuse_planner.reusable_fact_keys(staging, environment) if environment is not None else []
        if deadline_slack_ns is not None and deadline_slack_ns < 0:
            staged = StagedGraphMutation(
                success=False,
                error_code="SCHEDULER_DEADLINE_UNSATISFIABLE",
                event=event,
                graph=staging,
                impacted_nodes=impacted,
                deadline_reassignment=deadlines,
                reusable_fact_keys=reusable_fact_keys,
                base_revision=base_revision,
                deadline_budget_ns=deadline_budget_ns,
                required_runtime_budget_ns=required_runtime_budget_ns,
                deadline_slack_ns=deadline_slack_ns,
            )
            self._audit_staged(staged)
            return staged
        if not self.deadline_protector.validate(staging):
            staged = StagedGraphMutation(
                success=False,
                error_code="SCHEDULER_DEADLINE_UNSATISFIABLE",
                event=event,
                graph=staging,
                impacted_nodes=impacted,
                deadline_reassignment=deadlines,
                reusable_fact_keys=reusable_fact_keys,
                base_revision=base_revision,
                deadline_budget_ns=deadline_budget_ns,
                required_runtime_budget_ns=required_runtime_budget_ns,
                deadline_slack_ns=deadline_slack_ns,
            )
            self._audit_staged(staged)
            return staged
        staged = StagedGraphMutation(
            True,
            event,
            staging,
            impacted,
            deadlines,
            reusable_fact_keys=reusable_fact_keys,
            base_revision=base_revision,
            deadline_budget_ns=deadline_budget_ns,
            required_runtime_budget_ns=required_runtime_budget_ns,
            deadline_slack_ns=deadline_slack_ns,
        )
        self._audit_staged(staged)
        return staged

    def commit_staged_mutation(self, graph_store, staged: StagedGraphMutation) -> dict[str, Any]:
        if not staged.success:
            result = staged.to_dict()
            self._audit_rejected(staged, result)
            return result
        if staged.base_revision is not None and graph_store.revision != staged.base_revision:
            result = {
                "success": False,
                "error_code": "SCHEDULER_GRAPH_REVISION_CONFLICT",
                "task_graph_id": staged.graph.task_graph_id,
                "base_revision": staged.base_revision,
                "current_revision": graph_store.revision,
                "event": staged.event.to_dict(),
            }
            self._audit_rejected(staged, result)
            return result
        staged.graph.attach_dependencies()
        validate_acyclic(staged.graph)
        graph_store.global_dag.graphs[staged.graph.task_graph_id] = staged.graph
        for node_id, node in staged.graph.nodes.items():
            graph_store.global_dag.nodes[node_id] = node
        graph_store.mark_dirty_nodes(staged.impacted_nodes)
        graph_store.apply_changed_nodes(staged.impacted_nodes)
        result = {
            "success": True,
            "task_graph_id": staged.graph.task_graph_id,
            "committed_revision": graph_store.revision,
            "dirty_nodes_refreshed": sorted(staged.impacted_nodes),
            "reusable_fact_keys": list(staged.reusable_fact_keys),
            "deadline_budget_ns": staged.deadline_budget_ns,
            "required_runtime_budget_ns": staged.required_runtime_budget_ns,
            "deadline_slack_ns": staged.deadline_slack_ns,
        }
        self.audit.emit(
            "scheduler.reconstruction.committed",
            success=True,
            task_graph_id=staged.graph.task_graph_id,
            dynamic_event_id=staged.event.event_id,
            dynamic_event_type=staged.event.event_type,
            impacted_nodes=sorted(staged.impacted_nodes),
            dirty_nodes_refreshed=result["dirty_nodes_refreshed"],
            reusable_fact_keys=list(staged.reusable_fact_keys),
            committed_revision=graph_store.revision,
            base_revision=staged.base_revision,
            deadline_budget_ns=staged.deadline_budget_ns,
            required_runtime_budget_ns=staged.required_runtime_budget_ns,
            deadline_slack_ns=staged.deadline_slack_ns,
        )
        return result

    def _audit_staged(self, staged: StagedGraphMutation) -> None:
        self.audit.emit(
            "scheduler.reconstruction.staged",
            success=staged.success,
            error_code=staged.error_code,
            task_graph_id=staged.graph.task_graph_id,
            dynamic_event_id=staged.event.event_id,
            dynamic_event_type=staged.event.event_type,
            fact_key=staged.event.fact_key,
            node_id=staged.event.node_id,
            impacted_nodes=sorted(staged.impacted_nodes),
            deadline_reassignment_count=len(staged.deadline_reassignment),
            deadline_budget_ns=staged.deadline_budget_ns,
            required_runtime_budget_ns=staged.required_runtime_budget_ns,
            deadline_slack_ns=staged.deadline_slack_ns,
            reusable_fact_keys=list(staged.reusable_fact_keys),
            base_revision=staged.base_revision,
        )

    def _audit_rejected(self, staged: StagedGraphMutation, result: dict[str, Any]) -> None:
        self.audit.emit(
            "scheduler.reconstruction.rejected",
            success=False,
            error_code=str(result.get("error_code") or staged.error_code),
            task_graph_id=staged.graph.task_graph_id,
            dynamic_event_id=staged.event.event_id,
            dynamic_event_type=staged.event.event_type,
            impacted_nodes=sorted(staged.impacted_nodes),
            base_revision=result.get("base_revision", staged.base_revision),
            current_revision=result.get("current_revision", ""),
            deadline_budget_ns=staged.deadline_budget_ns,
            required_runtime_budget_ns=staged.required_runtime_budget_ns,
            deadline_slack_ns=staged.deadline_slack_ns,
        )
