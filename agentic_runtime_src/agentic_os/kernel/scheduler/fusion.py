from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from agentic_os.kernel.system_call import LLMQuery
from agentic_os.kernel.system_call.models import monotonic_id

from .audit import SchedulerAudit
from .critical_path import validate_acyclic
from .environment import EnvironmentStore
from .errors import SchedulerError, SchedulerResult
from .global_dag import GlobalGoalDAG
from .models import EdgeType, QueryType, TaskNodeStatus, now_ns, stable_hash_payload
from .opportunity import OpportunityIndex
from .preconditions import PreconditionEvaluator
from .reuse import ReuseEdge
from .task_graph import TaskGraph, TypedEdge
from .task_graph_planner import extract_llm_json_object


FUSION_REASONING_SCHEMA_ID = "fusion_reasoning.schema.json"


@dataclass(frozen=True)
class NodeInsertion:
    node_id: str
    after_node_id: str = ""
    before_node_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class NodeReordering:
    node_id: str
    old_after_node_id: str = ""
    new_after_node_id: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class FusionPlan:
    fusion_plan_id: str
    incoming_graph_id: str
    base_global_dag_revision: int
    accepted: bool
    reason: str
    reject_reason: str = ""
    reuse_edges: list[ReuseEdge] = field(default_factory=list)
    insertions: list[NodeInsertion] = field(default_factory=list)
    reorderings: list[NodeReordering] = field(default_factory=list)
    blocked_nodes: list[str] = field(default_factory=list)
    coverage_impact: dict[str, Any] = field(default_factory=dict)
    resource_impact: dict[str, Any] = field(default_factory=dict)
    safety_impact: dict[str, Any] = field(default_factory=dict)
    required_audit_events: list[str] = field(default_factory=list)
    audit_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fusion_plan_id": self.fusion_plan_id,
            "incoming_graph_id": self.incoming_graph_id,
            "base_global_dag_revision": self.base_global_dag_revision,
            "accepted": self.accepted,
            "reason": self.reason,
            "reject_reason": self.reject_reason,
            "reuse_edges": [edge.to_dict() for edge in self.reuse_edges],
            "insertions": [item.to_dict() for item in self.insertions],
            "reorderings": [item.to_dict() for item in self.reorderings],
            "blocked_nodes": list(self.blocked_nodes),
            "coverage_impact": dict(self.coverage_impact),
            "resource_impact": dict(self.resource_impact),
            "safety_impact": dict(self.safety_impact),
            "required_audit_events": list(self.required_audit_events),
            "audit_metadata": dict(self.audit_metadata),
        }


@dataclass(frozen=True)
class FusionCommitResult:
    success: bool
    fusion_plan_id: str
    task_graph_id: str
    committed_revision: int | None = None
    error_code: str = ""
    retry_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GoalFusionEngine:
    def __init__(self, *, audit: SchedulerAudit | None = None, schema_root: Path | None = None, kernel_service: Any | None = None) -> None:
        self.audit = audit or SchedulerAudit()
        self.schema_root = schema_root or Path(__file__).with_name("schemas")
        self.kernel_service = kernel_service
        self._plans: list[FusionPlan] = []

    def find_opportunities(
        self,
        *,
        global_dag: GlobalGoalDAG,
        incoming_graph: TaskGraph,
        environment: EnvironmentStore,
        opportunity_index: OpportunityIndex,
    ) -> FusionPlan:
        self.audit.emit(
            "scheduler.fusion.proposed",
            task_graph_id=incoming_graph.task_graph_id,
            agent_id=incoming_graph.agent_id,
            app_id=incoming_graph.app_id,
            session_id=incoming_graph.session_id,
        )
        reuse_edges: list[ReuseEdge] = []
        blocked_nodes: list[str] = []
        for node in incoming_graph.nodes.values():
            for fact_key in node.consumes_facts:
                fact = environment.get(fact_key)
                requirements = _reuse_requirements(node, fact_key)
                accepted, flags = environment.validate_reuse(
                    fact_key,
                    min_confidence=requirements["min_confidence"],
                    schema_id=requirements["schema_id"],
                )
                edge = ReuseEdge(
                    producer_node_id=fact.source_node_id if fact else str(flags.get("source_node_id") or ""),
                    consumer_node_id=node.node_id,
                    fact_key=fact_key,
                    fact_id=fact.fact_id if fact else str(flags.get("fact_id") or ""),
                    ttl_ok=bool(flags.get("ttl_ok", False)),
                    confidence_ok=bool(flags.get("confidence_ok", False)),
                    schema_ok=bool(flags.get("schema_ok", False)),
                    world_epoch_ok=bool(flags.get("world_epoch_ok", False)),
                    source_real_ok=bool(flags.get("source_real_ok", False)),
                    accepted=accepted,
                    reject_reason=str(flags.get("reject_reason") or ""),
                )
                reuse_edges.append(edge)
                self.audit.emit(
                    "scheduler.fusion.reuse_edge.accepted" if accepted else "scheduler.fusion.reuse_edge.rejected",
                    success=accepted,
                    error_code="" if accepted else edge.reject_reason,
                    task_graph_id=incoming_graph.task_graph_id,
                    node_id=node.node_id,
                    fact_key=fact_key,
                    fact_id=edge.fact_id,
                    required_schema_id=requirements["schema_id"],
                    min_confidence=requirements["min_confidence"],
                )
                if accepted:
                    self.audit.emit(
                        "scheduler.environment.fact_reused",
                        task_graph_id=incoming_graph.task_graph_id,
                        node_id=node.node_id,
                        fact_key=fact_key,
                        fact_id=edge.fact_id,
                        source_node_id=edge.producer_node_id,
                        required_schema_id=requirements["schema_id"],
                        min_confidence=requirements["min_confidence"],
                    )
                elif edge.reject_reason == "SCHEDULER_REUSE_TTL_OK_FAILED":
                    self.audit.emit(
                        "scheduler.fusion.stale_reuse_rejected",
                        success=False,
                        error_code=edge.reject_reason,
                        task_graph_id=incoming_graph.task_graph_id,
                        node_id=node.node_id,
                        fact_key=fact_key,
                        fact_id=edge.fact_id,
                        source_node_id=edge.producer_node_id,
                        required_schema_id=requirements["schema_id"],
                        min_confidence=requirements["min_confidence"],
                    )
                if not accepted:
                    blocked_nodes.append(node.node_id)
        timestamp = now_ns()
        coverage_impact = _coverage_impact(global_dag, incoming_graph)
        windows, window_rejections = _opportunity_windows(
            global_dag,
            incoming_graph,
            opportunity_index,
            environment=environment,
            at_ns=timestamp,
        )
        unique_window_count = len(_unique_windows(windows))
        physical_opportunity_required = _requires_physical_opportunity(incoming_graph)
        missing_resource_window_ids = _missing_window_resource_ids(incoming_graph, windows)
        resource_window_ok = not missing_resource_window_ids
        reuse_accepted = bool(reuse_edges) and all(edge.accepted for edge in reuse_edges)
        opportunity_ok = (not physical_opportunity_required) or (unique_window_count > 0 and resource_window_ok)
        accepted = reuse_accepted and opportunity_ok
        if accepted:
            reject_reason = ""
            reason = "fact_reuse_available"
        elif reuse_accepted and physical_opportunity_required and unique_window_count < 1:
            reject_reason = _window_reject_reason(window_rejections)
            reason = "no_safe_opportunity_window"
            blocked_nodes.extend(_physical_opportunity_node_ids(incoming_graph))
        elif reuse_accepted and physical_opportunity_required and not resource_window_ok:
            reject_reason = "SCHEDULER_FUSION_RESOURCE_WINDOW_UNAVAILABLE"
            reason = "no_safe_resource_window"
            blocked_nodes.extend(_resource_window_blocked_node_ids(incoming_graph, missing_resource_window_ids))
        else:
            reject_reason = _fusion_reject_reason(reuse_edges)
            reason = "no_verified_reuse_edge"
        score_components = _fusion_score_components(
            incoming_graph=incoming_graph,
            reuse_edges=reuse_edges,
            coverage_impact=coverage_impact,
            windows=windows,
            at_ns=timestamp,
        )
        score_inputs = _fusion_score_inputs(
            incoming_graph=incoming_graph,
            reuse_edges=reuse_edges,
            coverage_impact=coverage_impact,
            windows=windows,
        )
        plan = FusionPlan(
            fusion_plan_id=monotonic_id("fusion"),
            incoming_graph_id=incoming_graph.task_graph_id,
            base_global_dag_revision=global_dag.revision,
            accepted=accepted,
            reason=reason,
            reject_reason=reject_reason,
            reuse_edges=reuse_edges,
            insertions=[
                NodeInsertion(
                    node_id=node.node_id,
                    after_node_id=windows[0].start_after_node_id if windows else "",
                    before_node_id=windows[0].end_before_node_id if windows else "",
                )
                for node in incoming_graph.nodes.values()
            ],
            blocked_nodes=sorted(set(blocked_nodes)),
            coverage_impact=coverage_impact,
            resource_impact={
                "incoming_resource_count": sum(len(node.resources) for node in incoming_graph.nodes.values()),
                "matched_resource_window_count": int(score_inputs["matched_resource_window_count"]),
                "missing_resource_window_ids": missing_resource_window_ids,
                "resource_window_ok": resource_window_ok,
                "opportunity_window_required": physical_opportunity_required,
                "matched_opportunity_window_count": unique_window_count,
            },
            safety_impact={
                "safety_classes": sorted({node.safety_class for node in incoming_graph.nodes.values()}),
                "safety_risk_penalty": score_components["safety_risk_penalty"],
            },
            required_audit_events=["scheduler.fusion.accepted" if accepted else "scheduler.fusion.rejected"],
            audit_metadata={
                "opportunity_window_count": len(windows),
                "opportunity_window_required": physical_opportunity_required,
                "rejected_opportunity_window_count": len(window_rejections),
                "opportunity_window_rejections": window_rejections,
                "missing_resource_window_ids": missing_resource_window_ids,
                "resource_window_ok": resource_window_ok,
                "reject_reason": reject_reason,
                "fusion_score": score_components["fusion_score"],
                "fusion_score_components": score_components,
                "fusion_score_inputs": score_inputs,
            },
        )
        self.validate_plan(plan)
        self._plans.append(plan)
        if _coverage_preserved(coverage_impact):
            self.audit.emit(
                "scheduler.fusion.coverage_preserved",
                success=True,
                task_graph_id=incoming_graph.task_graph_id,
                agent_id=incoming_graph.agent_id,
                app_id=incoming_graph.app_id,
                session_id=incoming_graph.session_id,
                fusion_plan_id=plan.fusion_plan_id,
                before_count=len(coverage_impact.get("before", [])),
                after_count=len(coverage_impact.get("after", [])),
            )
        else:
            self.audit.emit(
                "scheduler.fusion.coverage_risk",
                success=False,
                error_code="SCHEDULER_FUSION_COVERAGE_RISK",
                task_graph_id=incoming_graph.task_graph_id,
                agent_id=incoming_graph.agent_id,
                app_id=incoming_graph.app_id,
                session_id=incoming_graph.session_id,
                fusion_plan_id=plan.fusion_plan_id,
            )
        if plan.accepted:
            for insertion in plan.insertions:
                self.audit.emit(
                    "scheduler.fusion.node_inserted",
                    success=True,
                    task_graph_id=incoming_graph.task_graph_id,
                    agent_id=incoming_graph.agent_id,
                    app_id=incoming_graph.app_id,
                    session_id=incoming_graph.session_id,
                    fusion_plan_id=plan.fusion_plan_id,
                    node_id=insertion.node_id,
                    after_node_id=insertion.after_node_id,
                    before_node_id=insertion.before_node_id,
                )
            for reordering in plan.reorderings:
                self.audit.emit(
                    "scheduler.fusion.node_reordered",
                    success=True,
                    task_graph_id=incoming_graph.task_graph_id,
                    agent_id=incoming_graph.agent_id,
                    app_id=incoming_graph.app_id,
                    session_id=incoming_graph.session_id,
                    fusion_plan_id=plan.fusion_plan_id,
                    node_id=reordering.node_id,
                    old_after_node_id=reordering.old_after_node_id,
                    new_after_node_id=reordering.new_after_node_id,
                    reason=reordering.reason,
                )
        self.audit.emit(
            "scheduler.fusion.accepted" if plan.accepted else "scheduler.fusion.rejected",
            success=plan.accepted,
            error_code="" if plan.accepted else "SCHEDULER_FUSION_REJECTED",
            task_graph_id=incoming_graph.task_graph_id,
            agent_id=incoming_graph.agent_id,
            app_id=incoming_graph.app_id,
            session_id=incoming_graph.session_id,
            fusion_plan_id=plan.fusion_plan_id,
            reason=plan.reason,
            reject_reason=plan.reject_reason,
            fusion_score=plan.audit_metadata.get("fusion_score", 0),
            fusion_score_components=plan.audit_metadata.get("fusion_score_components", {}),
        )
        return plan

    def explain_plan_with_real_llm(
        self,
        plan: FusionPlan,
        *,
        incoming_graph: TaskGraph,
        global_dag: GlobalGoalDAG,
        kernel_service: Any | None = None,
        agent_name: str = "",
        timeout_s: float = 60.0,
    ) -> SchedulerResult:
        service = kernel_service or self.kernel_service
        if service is None:
            result = SchedulerResult.error("SCHEDULER_LLM_REAL_PROVIDER_REQUIRED", upstream_error_code="SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE")
            self._record_llm_reasoning_failure(plan, result)
            return result
        query = LLMQuery(
            operation_type="scheduler_explain_fusion_plan",
            params={
                "schema_id": FUSION_REASONING_SCHEMA_ID,
                "fusion_plan_id": plan.fusion_plan_id,
                "incoming_graph_id": plan.incoming_graph_id,
            },
            messages=[
                {"role": "system", "content": _fusion_reasoning_system_prompt()},
                {"role": "user", "content": _fusion_reasoning_prompt(plan, incoming_graph=incoming_graph, global_dag=global_dag)},
            ],
            response_format={"type": "json_object"},
            action_type="scheduler_planning",
            metadata={
                "agent_id": incoming_graph.agent_id,
                "app_id": incoming_graph.app_id,
                "session_id": incoming_graph.session_id,
                "task_graph_id": incoming_graph.task_graph_id,
                "fusion_plan_id": plan.fusion_plan_id,
                "scheduler_component": "goal_fusion_engine",
                "permissions": ["llm.external.call"],
            },
        )
        self.audit.emit(
            "scheduler.llm.real_call_started",
            agent_id=incoming_graph.agent_id,
            app_id=incoming_graph.app_id,
            session_id=incoming_graph.session_id,
            task_graph_id=incoming_graph.task_graph_id,
            operation_type=query.operation_type,
            action_type=query.action_type,
            schema_id=FUSION_REASONING_SCHEMA_ID,
            fusion_plan_id=plan.fusion_plan_id,
            success=True,
        )
        try:
            response = service.execute_request(agent_name or incoming_graph.app_id, query, timeout_s=timeout_s)
        except Exception as exc:
            result = SchedulerResult.error(
                "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED",
                upstream_error_code="SCHEDULER_DISPATCH_FAILED",
                exception=_exception_summary(exc),
            )
            self.audit.emit(
                "scheduler.llm.real_call_failed",
                success=False,
                error_code=result.error_code,
                agent_id=incoming_graph.agent_id,
                app_id=incoming_graph.app_id,
                session_id=incoming_graph.session_id,
                task_graph_id=incoming_graph.task_graph_id,
                operation_type=query.operation_type,
                action_type=query.action_type,
                schema_id=FUSION_REASONING_SCHEMA_ID,
                fusion_plan_id=plan.fusion_plan_id,
                upstream_error_code="SCHEDULER_DISPATCH_FAILED",
                exception=result.metadata["exception"],
            )
            self._record_llm_reasoning_failure(plan, result)
            return result

        syscall_id = getattr(getattr(response, "syscall", None), "syscall_id", "")
        if not response.success:
            result = SchedulerResult.error(
                "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED",
                upstream_error_code=response.error_code,
                syscall_id=syscall_id,
            )
            self.audit.emit(
                "scheduler.llm.real_call_failed",
                success=False,
                error_code=result.error_code,
                agent_id=incoming_graph.agent_id,
                app_id=incoming_graph.app_id,
                session_id=incoming_graph.session_id,
                task_graph_id=incoming_graph.task_graph_id,
                syscall_id=syscall_id,
                operation_type=query.operation_type,
                action_type=query.action_type,
                schema_id=FUSION_REASONING_SCHEMA_ID,
                fusion_plan_id=plan.fusion_plan_id,
                upstream_error_code=response.error_code,
            )
            self._record_llm_reasoning_failure(plan, result)
            return result

        try:
            payload = extract_llm_json_object(response.response)
            payload = _normalize_fusion_reasoning_payload(payload, plan)
            self._validate_fusion_reasoning_payload(payload, plan)
        except (SchedulerError, ValidationError, ValueError, TypeError) as exc:
            result = SchedulerResult.error(
                "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID",
                syscall_id=syscall_id,
                exception=_exception_summary(exc),
            )
            self.audit.emit(
                "scheduler.llm.real_call_failed",
                success=False,
                error_code=result.error_code,
                agent_id=incoming_graph.agent_id,
                app_id=incoming_graph.app_id,
                session_id=incoming_graph.session_id,
                task_graph_id=incoming_graph.task_graph_id,
                syscall_id=syscall_id,
                operation_type=query.operation_type,
                action_type=query.action_type,
                schema_id=FUSION_REASONING_SCHEMA_ID,
                fusion_plan_id=plan.fusion_plan_id,
                exception=result.metadata["exception"],
            )
            self._record_llm_reasoning_failure(plan, result)
            return result

        reasoning = {
            "status": "completed",
            "schema_id": FUSION_REASONING_SCHEMA_ID,
            "syscall_id": syscall_id,
            "model": str(getattr(response, "metadata", {}).get("model") or ""),
            "response_summary": _payload_summary(payload),
        }
        plan.audit_metadata["llm_reasoning"] = reasoning
        self.audit.emit(
            "scheduler.llm.real_call_completed",
            agent_id=incoming_graph.agent_id,
            app_id=incoming_graph.app_id,
            session_id=incoming_graph.session_id,
            task_graph_id=incoming_graph.task_graph_id,
            syscall_id=syscall_id,
            operation_type=query.operation_type,
            action_type=query.action_type,
            schema_id=FUSION_REASONING_SCHEMA_ID,
            fusion_plan_id=plan.fusion_plan_id,
            response_summary=reasoning["response_summary"],
            success=True,
        )
        return SchedulerResult.ok(reasoning, fusion_plan_id=plan.fusion_plan_id, syscall_id=syscall_id)

    def validate_plan(self, plan: FusionPlan) -> None:
        schema_path = self.schema_root / "fusion_plan.schema.json"
        if not schema_path.exists():
            return
        from jsonschema import Draft202012Validator

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(plan.to_dict())
        if plan.accepted:
            for edge in plan.reuse_edges:
                if not all((edge.ttl_ok, edge.confidence_ok, edge.schema_ok, edge.world_epoch_ok, edge.source_real_ok)):
                    raise ValueError(f"accepted fusion plan has rejected reuse edge: {edge.fact_key}")
            if not _coverage_preserved(plan.coverage_impact):
                raise ValueError("accepted fusion plan does not preserve coverage requirements")
            score_inputs = dict(plan.audit_metadata.get("fusion_score_inputs") or {})
            if plan.audit_metadata.get("opportunity_window_required") and int(score_inputs.get("unique_opportunity_window_count") or 0) < 1:
                raise ValueError("SCHEDULER_FUSION_OPPORTUNITY_WINDOW_REQUIRED")
            if list(plan.resource_impact.get("missing_resource_window_ids") or []):
                raise ValueError("SCHEDULER_FUSION_RESOURCE_WINDOW_UNAVAILABLE")
        elif not plan.reject_reason:
            raise ValueError("rejected fusion plan must include reject_reason")

    def _validate_fusion_reasoning_payload(self, payload: dict[str, Any], plan: FusionPlan) -> None:
        schema = json.loads((self.schema_root / FUSION_REASONING_SCHEMA_ID).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(payload)
        if payload.get("fusion_plan_id") != plan.fusion_plan_id:
            raise ValueError("fusion reasoning plan identifier mismatch")

    def _record_llm_reasoning_failure(self, plan: FusionPlan, result: SchedulerResult) -> None:
        plan.audit_metadata["llm_reasoning"] = {
            "status": "failed",
            "schema_id": FUSION_REASONING_SCHEMA_ID,
            "error_code": result.error_code,
            "upstream_error_code": result.metadata.get("upstream_error_code", ""),
            "syscall_id": result.metadata.get("syscall_id", ""),
            "exception": result.metadata.get("exception", {}),
        }

    def apply_to_graph(self, graph: TaskGraph, plan: FusionPlan) -> None:
        for edge in plan.reuse_edges:
            if edge.accepted:
                graph.edges.append(
                    TypedEdge(
                        edge_id=monotonic_id("edge"),
                        source_id=edge.producer_node_id,
                        target_id=edge.consumer_node_id,
                        edge_type=EdgeType.REUSES_FACT,
                        fact_key=edge.fact_key,
                        metadata={"fact_id": edge.fact_id, "fusion_plan_id": plan.fusion_plan_id},
                    )
                )
        for insertion in plan.insertions:
            if insertion.after_node_id:
                graph.edges.append(
                    TypedEdge(
                        edge_id=monotonic_id("edge"),
                        source_id=insertion.after_node_id,
                        target_id=insertion.node_id,
                        edge_type=EdgeType.PRECEDENCE,
                        metadata={
                            "fusion_plan_id": plan.fusion_plan_id,
                            "insertion": "after",
                            "cross_graph_dependency": insertion.after_node_id not in graph.nodes,
                        },
                    )
                )
            if insertion.before_node_id:
                graph.edges.append(
                    TypedEdge(
                        edge_id=monotonic_id("edge"),
                        source_id=insertion.node_id,
                        target_id=insertion.before_node_id,
                        edge_type=EdgeType.PRECEDENCE,
                        metadata={
                            "fusion_plan_id": plan.fusion_plan_id,
                            "insertion": "before",
                            "cross_graph_dependency": insertion.before_node_id not in graph.nodes,
                        },
                    )
                )

    def commit_fusion(self, graph_store, incoming_graph: TaskGraph, plan: FusionPlan) -> FusionCommitResult:
        if not plan.accepted:
            return self._commit_rejected(
                plan,
                incoming_graph,
                "SCHEDULER_FUSION_PLAN_NOT_ACCEPTED",
                metadata={"reject_reason": plan.reject_reason},
            )
        if graph_store.revision != plan.base_global_dag_revision:
            return self._commit_rejected(
                plan,
                incoming_graph,
                "SCHEDULER_FUSION_REBASE_REQUIRED",
                retry_required=True,
                metadata={
                    "base_global_dag_revision": plan.base_global_dag_revision,
                    "current_global_dag_revision": graph_store.revision,
                    "legacy_error_code": "SCHEDULER_FUSION_REVISION_CONFLICT",
                },
            )
        try:
            self.validate_plan(plan)
            staged_graph = self._stage_incoming_graph(incoming_graph, plan)
            staging = graph_store.snapshot_metadata()
            self._validate_staged_global_dag(staging, staged_graph, plan)
        except ValueError as exc:
            return self._commit_rejected(plan, incoming_graph, str(exc) or "SCHEDULER_FUSION_COMMIT_INVALID")

        graph_store.add_graph(staged_graph)
        self.audit.emit(
            "scheduler.fusion.commit_accepted",
            success=True,
            task_graph_id=staged_graph.task_graph_id,
            agent_id=staged_graph.agent_id,
            app_id=staged_graph.app_id,
            session_id=staged_graph.session_id,
            fusion_plan_id=plan.fusion_plan_id,
            committed_revision=graph_store.revision,
        )
        return FusionCommitResult(
            success=True,
            fusion_plan_id=plan.fusion_plan_id,
            task_graph_id=staged_graph.task_graph_id,
            committed_revision=graph_store.revision,
        )

    def _stage_incoming_graph(self, incoming_graph: TaskGraph, plan: FusionPlan) -> TaskGraph:
        staged_graph = deepcopy(incoming_graph)
        self.apply_to_graph(staged_graph, plan)
        staged_graph.attach_dependencies()
        validate_acyclic(staged_graph)
        self._validate_resources(staged_graph)
        self._validate_safety(staged_graph)
        self._validate_deadlines(staged_graph)
        return staged_graph

    def _validate_staged_global_dag(self, staging: GlobalGoalDAG, staged_graph: TaskGraph, plan: FusionPlan) -> None:
        if staged_graph.task_graph_id in staging.graphs:
            raise ValueError("SCHEDULER_FUSION_DUPLICATE_GRAPH_ID")
        duplicate_nodes = sorted(set(staged_graph.nodes) & set(staging.nodes))
        if duplicate_nodes:
            raise ValueError("SCHEDULER_FUSION_DUPLICATE_NODE_ID")
        consumer_nodes = set(staged_graph.nodes)
        for insertion in plan.insertions:
            if insertion.node_id not in staged_graph.nodes:
                raise ValueError("SCHEDULER_FUSION_INSERTION_NODE_MISSING")
            if insertion.after_node_id and insertion.after_node_id not in staging.nodes and insertion.after_node_id not in staged_graph.nodes:
                raise ValueError("SCHEDULER_FUSION_INSERTION_ANCHOR_MISSING")
            if insertion.before_node_id and insertion.before_node_id not in staging.nodes and insertion.before_node_id not in staged_graph.nodes:
                raise ValueError("SCHEDULER_FUSION_INSERTION_ANCHOR_MISSING")
            if insertion.before_node_id and insertion.before_node_id in staging.nodes:
                before_node = staging.nodes[insertion.before_node_id]
                if before_node.status not in {TaskNodeStatus.ADMITTED, TaskNodeStatus.WAITING, TaskNodeStatus.BLOCKED, TaskNodeStatus.READY}:
                    raise ValueError("SCHEDULER_FUSION_CROSS_GRAPH_REORDER_UNSUPPORTED")
        for edge in plan.reuse_edges:
            if not edge.accepted:
                continue
            if not edge.producer_node_id:
                raise ValueError("SCHEDULER_FUSION_REUSE_PRODUCER_MISSING")
            if edge.producer_node_id not in staging.nodes:
                raise ValueError("SCHEDULER_FUSION_REUSE_PRODUCER_NOT_IN_DAG")
            if edge.consumer_node_id not in consumer_nodes:
                raise ValueError("SCHEDULER_FUSION_REUSE_CONSUMER_MISSING")
            if not edge.fact_id:
                raise ValueError("SCHEDULER_FUSION_REUSE_FACT_ID_MISSING")
        if not _coverage_preserved(plan.coverage_impact):
            raise ValueError("SCHEDULER_FUSION_COVERAGE_RISK")
        staging.graphs[staged_graph.task_graph_id] = staged_graph
        staging.nodes.update(staged_graph.nodes)
        staging.rebuild_indexes()
        _validate_global_dag_acyclic(staging)

    def _validate_resources(self, graph: TaskGraph) -> None:
        for node in graph.nodes.values():
            for request in node.resources:
                if not request.resource_id:
                    raise ValueError("SCHEDULER_FUSION_RESOURCE_INVALID")
                if request.amount <= 0 or request.lease_ttl_ns <= 0:
                    raise ValueError("SCHEDULER_FUSION_RESOURCE_INVALID")
                if request.mode not in {"exclusive", "shared"}:
                    raise ValueError("SCHEDULER_FUSION_RESOURCE_INVALID")

    def _validate_safety(self, graph: TaskGraph) -> None:
        for node in graph.nodes.values():
            if not node.safety_class:
                raise ValueError("SCHEDULER_FUSION_SAFETY_INVALID")
            if not isinstance(node.safety_constraints, dict):
                raise ValueError("SCHEDULER_FUSION_SAFETY_INVALID")

    def _validate_deadlines(self, graph: TaskGraph) -> None:
        timestamp = now_ns()
        if graph.deadline_ns is not None and graph.deadline_ns < timestamp:
            raise ValueError("SCHEDULER_FUSION_DEADLINE_INVALID")
        for node in graph.nodes.values():
            if node.deadline_ns is not None and node.deadline_ns < timestamp:
                raise ValueError("SCHEDULER_FUSION_DEADLINE_INVALID")
            if node.runtime_budget_ns is not None and node.runtime_budget_ns <= 0:
                raise ValueError("SCHEDULER_FUSION_DEADLINE_INVALID")
            if node.status in {TaskNodeStatus.FAILED, TaskNodeStatus.CANCELLED, TaskNodeStatus.STALE, TaskNodeStatus.REJECTED}:
                raise ValueError("SCHEDULER_FUSION_NODE_TERMINAL_INVALID")

    def _commit_rejected(
        self,
        plan: FusionPlan,
        graph: TaskGraph,
        error_code: str,
        *,
        retry_required: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> FusionCommitResult:
        self.audit.emit(
            "scheduler.fusion.commit_rejected",
            success=False,
            error_code=error_code,
            task_graph_id=graph.task_graph_id,
            agent_id=graph.agent_id,
            app_id=graph.app_id,
            session_id=graph.session_id,
            fusion_plan_id=plan.fusion_plan_id,
            retry_required=retry_required,
            **dict(metadata or {}),
        )
        return FusionCommitResult(
            success=False,
            fusion_plan_id=plan.fusion_plan_id,
            task_graph_id=graph.task_graph_id,
            error_code=error_code,
            retry_required=retry_required,
            metadata=dict(metadata or {}),
        )

    def snapshot(self) -> list[dict[str, Any]]:
        return [plan.to_dict() for plan in self._plans[-25:]]


def _validate_global_dag_acyclic(global_dag: GlobalGoalDAG) -> None:
    indegree = {node_id: 0 for node_id in global_dag.nodes}
    for source_id, targets in global_dag.edges.items():
        if source_id not in indegree:
            raise ValueError("SCHEDULER_FUSION_INSERTION_ANCHOR_MISSING")
        for target_id in targets:
            if target_id not in indegree:
                raise ValueError("SCHEDULER_FUSION_INSERTION_ANCHOR_MISSING")
            indegree[target_id] += 1

    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node_id = ready.pop(0)
        visited += 1
        for target_id in sorted(global_dag.edges.get(node_id, set())):
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                ready.append(target_id)
                ready.sort()
    if visited != len(indegree):
        raise ValueError("SCHEDULER_FUSION_CYCLE_REJECTED")


def _coverage_impact(global_dag: GlobalGoalDAG, incoming_graph: TaskGraph) -> dict[str, Any]:
    before: list[dict[str, Any]] = []
    for graph in global_dag.graphs.values():
        before.extend(_coverage_entry(graph.task_graph_id, item.to_dict()) for item in graph.coverage_requirements)
    incoming = [_coverage_entry(incoming_graph.task_graph_id, item.to_dict()) for item in incoming_graph.coverage_requirements]
    after = before + incoming
    after_by_key = {item["requirement_key"]: item for item in after}
    requirement_impacts = [
        {
            "requirement_key": item["requirement_key"],
            "task_graph_id": item["task_graph_id"],
            "before": item["requirement"],
            "after": after_by_key.get(item["requirement_key"], {}).get("requirement"),
            "preserved": item["requirement_key"] in after_by_key,
        }
        for item in before
    ]
    return {
        "before": before,
        "incoming": incoming,
        "after": after,
        "requirements": requirement_impacts,
        "preserved": all(item["preserved"] for item in requirement_impacts),
    }


def _coverage_preserved(coverage_impact: dict[str, Any]) -> bool:
    before = {str(item.get("requirement_key") or json.dumps(item, sort_keys=True, default=str)) for item in list(coverage_impact.get("before") or [])}
    after = {str(item.get("requirement_key") or json.dumps(item, sort_keys=True, default=str)) for item in list(coverage_impact.get("after") or [])}
    return before.issubset(after)


def _coverage_entry(task_graph_id: str, requirement: dict[str, Any]) -> dict[str, Any]:
    key_parts = {
        "requirement_id": requirement.get("requirement_id") or "",
        "workspace_zone": requirement.get("workspace_zone") or "",
        "route_segment_id": requirement.get("route_segment_id") or "",
        "required": requirement.get("required", True),
        "metadata": requirement.get("metadata") or {},
    }
    return {
        "task_graph_id": task_graph_id,
        "requirement_key": stable_hash_payload(key_parts),
        "requirement": dict(requirement),
    }


def _fusion_reject_reason(reuse_edges: list[ReuseEdge]) -> str:
    if not reuse_edges:
        return "SCHEDULER_FUSION_NO_REUSE_EDGE"
    for edge in reuse_edges:
        if not edge.accepted:
            return edge.reject_reason or "SCHEDULER_FUSION_REUSE_EDGE_REJECTED"
    return "SCHEDULER_FUSION_REJECTED"


def _opportunity_windows(
    global_dag: GlobalGoalDAG,
    incoming_graph: TaskGraph,
    opportunity_index: OpportunityIndex,
    *,
    environment: EnvironmentStore,
    at_ns: int,
) -> tuple[list[Any], list[dict[str, Any]]]:
    windows, rejections = _matching_opportunity_windows(
        incoming_graph,
        opportunity_index,
        environment=environment,
        at_ns=at_ns,
    )
    if windows:
        return windows, rejections
    if rejections:
        return windows, rejections
    derived_index = OpportunityIndex()
    for graph in global_dag.graphs.values():
        derived_index.rebuild_from_graph(graph)
    derived_windows, derived_rejections = _matching_opportunity_windows(
        incoming_graph,
        derived_index,
        environment=environment,
        at_ns=at_ns,
    )
    return derived_windows, [*rejections, *derived_rejections]


def _matching_opportunity_windows(
    incoming_graph: TaskGraph,
    opportunity_index: OpportunityIndex,
    *,
    environment: EnvironmentStore,
    at_ns: int,
) -> tuple[list[Any], list[dict[str, Any]]]:
    windows: list[Any] = []
    rejections: list[dict[str, Any]] = []
    for node in incoming_graph.nodes.values():
        workspace_zone = node.workspace_zone or ""
        route_segment_id = node.route_segment_id or ""
        if not workspace_zone and not route_segment_id:
            continue
        for window in opportunity_index.find(workspace_zone=workspace_zone, route_segment_id=route_segment_id):
            window_result = _window_preconditions_ok(window, environment=environment, at_ns=at_ns)
            if window_result.success:
                windows.append(window)
                continue
            rejections.append(
                {
                    "window_id": str(getattr(window, "window_id", "") or ""),
                    "consumer_node_id": node.node_id,
                    "start_after_node_id": str(getattr(window, "start_after_node_id", "") or ""),
                    "end_before_node_id": str(getattr(window, "end_before_node_id", "") or ""),
                    "error_code": window_result.error_code,
                    "metadata": dict(window_result.metadata),
                }
            )
    return windows, rejections


def _window_preconditions_ok(window: Any, *, environment: EnvironmentStore, at_ns: int) -> SchedulerResult:
    required_preconditions = list(getattr(window, "required_preconditions", []) or [])
    if not required_preconditions:
        return SchedulerResult.ok()
    return PreconditionEvaluator(environment).evaluate(required_preconditions, at_ns)


def _window_reject_reason(window_rejections: list[dict[str, Any]]) -> str:
    for rejection in window_rejections:
        error_code = str(rejection.get("error_code") or "")
        if error_code:
            return error_code
    return "SCHEDULER_FUSION_OPPORTUNITY_WINDOW_REQUIRED"


def _requires_physical_opportunity(incoming_graph: TaskGraph) -> bool:
    if incoming_graph.route_intent is not None:
        return True
    return any(_node_requires_physical_opportunity(node) for node in incoming_graph.nodes.values())


def _physical_opportunity_node_ids(incoming_graph: TaskGraph) -> list[str]:
    return sorted(node.node_id for node in incoming_graph.nodes.values() if _node_requires_physical_opportunity(node))


def _node_requires_physical_opportunity(node: Any) -> bool:
    if getattr(node, "query_type", "") == QueryType.ROBOT_CAPABILITY:
        return True
    if list(getattr(node, "resources", []) or []):
        return True
    if getattr(node, "workspace_zone", None) or getattr(node, "route_segment_id", None):
        return True
    capability = str(getattr(node, "capability", "") or "")
    return capability.startswith(("robot.", "perception.", "manipulation.", "arm.", "gripper."))


def _fusion_score_components(
    *,
    incoming_graph: TaskGraph,
    reuse_edges: list[ReuseEdge],
    coverage_impact: dict[str, Any],
    windows: list[Any],
    at_ns: int,
) -> dict[str, int]:
    route_overlap_score = _route_overlap_score(windows)
    fact_reuse_score = 30 * sum(1 for edge in reuse_edges if edge.accepted)
    resource_window_score, resource_contention_penalty = _resource_window_scores(incoming_graph, windows)
    deadline_slack_score = _deadline_slack_score(incoming_graph, at_ns)
    coverage_preservation_score = _coverage_preservation_score(coverage_impact)
    user_priority_score = _user_priority_score(incoming_graph)
    safety_risk_penalty = _safety_risk_penalty(incoming_graph)
    coverage_loss_penalty = _coverage_loss_penalty(coverage_impact)
    fusion_score = (
        route_overlap_score
        + fact_reuse_score
        + resource_window_score
        + deadline_slack_score
        + coverage_preservation_score
        + user_priority_score
        - safety_risk_penalty
        - coverage_loss_penalty
        - resource_contention_penalty
    )
    return {
        "route_overlap_score": route_overlap_score,
        "fact_reuse_score": fact_reuse_score,
        "resource_window_score": resource_window_score,
        "deadline_slack_score": deadline_slack_score,
        "coverage_preservation_score": coverage_preservation_score,
        "user_priority_score": user_priority_score,
        "safety_risk_penalty": safety_risk_penalty,
        "coverage_loss_penalty": coverage_loss_penalty,
        "resource_contention_penalty": resource_contention_penalty,
        "fusion_score": fusion_score,
    }


def _fusion_score_inputs(
    *,
    incoming_graph: TaskGraph,
    reuse_edges: list[ReuseEdge],
    coverage_impact: dict[str, Any],
    windows: list[Any],
) -> dict[str, int]:
    resource_requests = _resource_requests(incoming_graph)
    matched_resource_count = 0
    for node in incoming_graph.nodes.values():
        available = _window_resource_ids(_windows_matching_node(node, windows))
        matched_resource_count += sum(1 for request in node.resources if request.resource_id and request.resource_id in available)
    return {
        "accepted_reuse_edge_count": sum(1 for edge in reuse_edges if edge.accepted),
        "rejected_reuse_edge_count": sum(1 for edge in reuse_edges if not edge.accepted),
        "opportunity_window_count": len(windows),
        "unique_opportunity_window_count": len(_unique_windows(windows)),
        "incoming_resource_count": len(resource_requests),
        "matched_resource_window_count": matched_resource_count,
        "coverage_before_count": len(list(coverage_impact.get("before") or [])),
        "coverage_after_count": len(list(coverage_impact.get("after") or [])),
    }


def _route_overlap_score(windows: list[Any]) -> int:
    score = 0
    for window in _unique_windows(windows):
        window_score = max(0, int(getattr(window, "score", 0) or 0))
        if getattr(window, "workspace_zone", ""):
            window_score = max(window_score, 10)
        if getattr(window, "route_segment_id", ""):
            window_score = max(window_score, 10)
        if getattr(window, "workspace_zone", "") and getattr(window, "route_segment_id", ""):
            window_score = max(window_score, 20)
        score += min(25, window_score)
    return _clamp(score, 0, 100)


def _resource_window_scores(incoming_graph: TaskGraph, windows: list[Any]) -> tuple[int, int]:
    resource_window_score = 0
    resource_contention_penalty = 0
    for node in incoming_graph.nodes.values():
        available = _window_resource_ids(_windows_matching_node(node, windows))
        for request in node.resources:
            if not request.resource_id:
                continue
            if request.resource_id in available:
                resource_window_score += 8
                continue
            resource_contention_penalty += 8 if request.mode == "exclusive" else 3
    return _clamp(resource_window_score, 0, 80), _clamp(resource_contention_penalty, 0, 100)


def _deadline_slack_score(incoming_graph: TaskGraph, at_ns: int) -> int:
    deadlines = [incoming_graph.deadline_ns] if incoming_graph.deadline_ns is not None else []
    deadlines.extend(node.deadline_ns for node in incoming_graph.nodes.values() if node.deadline_ns is not None)
    score = 0
    for deadline in deadlines:
        slack_ns = int(deadline) - at_ns
        if slack_ns <= 0:
            score -= 30
        else:
            score += max(1, min(20, int(slack_ns / 5_000_000_000)))
    return _clamp(score, -100, 100)


def _coverage_preservation_score(coverage_impact: dict[str, Any]) -> int:
    if not _coverage_preserved(coverage_impact):
        return 0
    return 20 if list(coverage_impact.get("before") or []) else 10


def _user_priority_score(incoming_graph: TaskGraph) -> int:
    score = int(incoming_graph.priority or 0)
    for node in incoming_graph.nodes.values():
        score += max(int(node.base_priority or 0), int(node.effective_priority or 0), int(node.inherited_priority or 0))
    return _clamp(score, -50, 100)


def _safety_risk_penalty(incoming_graph: TaskGraph) -> int:
    weights = {
        "emergency": 20,
        "safety": 15,
        "safety_monitor": 10,
        "human_safety": 20,
        "collision_risk": 25,
        "hazardous": 30,
        "dangerous": 30,
        "critical": 20,
    }
    penalty = 0
    for node in incoming_graph.nodes.values():
        penalty += weights.get(str(node.safety_class or "").lower(), 0)
        if node.safety_constraints:
            penalty += 10
    return _clamp(penalty, 0, 100)


def _coverage_loss_penalty(coverage_impact: dict[str, Any]) -> int:
    before = {str(item.get("requirement_key") or json.dumps(item, sort_keys=True, default=str)) for item in list(coverage_impact.get("before") or [])}
    after = {str(item.get("requirement_key") or json.dumps(item, sort_keys=True, default=str)) for item in list(coverage_impact.get("after") or [])}
    missing = before - after
    if not missing and _coverage_preserved(coverage_impact):
        return 0
    return max(40, len(missing) * 40)


def _resource_requests(incoming_graph: TaskGraph) -> list[Any]:
    return [request for node in incoming_graph.nodes.values() for request in node.resources if request.resource_id]


def _missing_window_resource_ids(incoming_graph: TaskGraph, windows: list[Any]) -> list[str]:
    missing: set[str] = set()
    for node in incoming_graph.nodes.values():
        available = _window_resource_ids(_windows_matching_node(node, windows))
        for request in node.resources:
            resource_id = str(request.resource_id or "")
            if resource_id and resource_id not in available:
                missing.add(resource_id)
    return sorted(missing)


def _resource_window_blocked_node_ids(incoming_graph: TaskGraph, missing_resource_ids: list[str]) -> list[str]:
    missing = set(missing_resource_ids)
    return sorted(
        node.node_id
        for node in incoming_graph.nodes.values()
        if any(str(request.resource_id or "") in missing for request in node.resources)
    )


def _windows_matching_node(node: Any, windows: list[Any]) -> list[Any]:
    workspace_zone = str(getattr(node, "workspace_zone", "") or "")
    route_segment_id = str(getattr(node, "route_segment_id", "") or "")
    if not workspace_zone and not route_segment_id:
        return []
    matches: list[Any] = []
    for window in windows:
        if workspace_zone and str(getattr(window, "workspace_zone", "") or "") != workspace_zone:
            continue
        if route_segment_id and str(getattr(window, "route_segment_id", "") or "") != route_segment_id:
            continue
        matches.append(window)
    return matches


def _window_resource_ids(windows: list[Any]) -> set[str]:
    resource_ids: set[str] = set()
    for window in windows:
        resource_ids.update(str(item) for item in list(getattr(window, "available_resources", []) or []) if item)
    return resource_ids


def _unique_windows(windows: list[Any]) -> list[Any]:
    unique: dict[str, Any] = {}
    for window in windows:
        key = str(getattr(window, "window_id", "") or "")
        if not key:
            key = stable_hash_payload(
                {
                    "route_segment_id": getattr(window, "route_segment_id", ""),
                    "workspace_zone": getattr(window, "workspace_zone", ""),
                    "start_after_node_id": getattr(window, "start_after_node_id", ""),
                    "end_before_node_id": getattr(window, "end_before_node_id", ""),
                    "available_resources": list(getattr(window, "available_resources", []) or []),
                }
            )
        unique.setdefault(key, window)
    return list(unique.values())


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _fusion_reasoning_system_prompt() -> str:
    return (
        "You are the AgenticOS scheduler fusion explainer. Return only JSON matching fusion_reasoning.schema.json. "
        "Do not invent facts, capabilities, robot poses, object poses, or successful actions. "
        "Explain whether the deterministic fusion evidence supports the already-computed plan; do not issue robot commands."
    )


def _fusion_reasoning_prompt(plan: FusionPlan, *, incoming_graph: TaskGraph, global_dag: GlobalGoalDAG) -> str:
    payload = {
        "fusion_plan_id": plan.fusion_plan_id,
        "incoming_graph_id": plan.incoming_graph_id,
        "incoming_task_graph_id": incoming_graph.task_graph_id,
        "global_dag_revision": global_dag.revision,
        "existing_graph_ids": sorted(global_dag.graphs),
        "accepted": plan.accepted,
        "reason": plan.reason,
        "reject_reason": plan.reject_reason,
        "blocked_nodes": list(plan.blocked_nodes),
        "reuse_edges": [edge.to_dict() for edge in plan.reuse_edges],
        "coverage_impact": plan.coverage_impact,
        "resource_impact": plan.resource_impact,
        "safety_impact": plan.safety_impact,
        "fusion_score_components": dict(plan.audit_metadata.get("fusion_score_components", {})),
        "required_output": {
            "fusion_plan_id": plan.fusion_plan_id,
            "decision_supported": "boolean",
            "risk_summary": "brief text; no private prompt or secret values",
            "required_audit_events": list(plan.required_audit_events),
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _payload_summary(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        keys = sorted(str(key) for key in payload)
    else:
        keys = []
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "sha256": stable_hash_payload(payload),
        "length": len(text),
        "keys": keys,
    }


def _normalize_fusion_reasoning_payload(payload: dict[str, Any], plan: FusionPlan) -> dict[str, Any]:
    normalized = dict(payload)
    decision = _coerce_bool(normalized.get("decision_supported"))
    if decision is None:
        decision = _find_bool_by_key(
            normalized,
            {
                "supports_existing_plan",
                "supports_plan",
                "supported",
                "is_supported",
                "plan_supported",
                "decision_supported",
            },
        )
    if decision is not None:
        normalized["decision_supported"] = decision

    risk_summary = normalized.get("risk_summary")
    if not isinstance(risk_summary, str) or not risk_summary:
        risk_summary = _find_text_by_key(
            normalized,
            {
                "risk_summary",
                "fusion_reason",
                "reasoning_summary",
                "summary",
                "details",
                "reason",
            },
        )
    if not risk_summary:
        evidence_keys = _find_evidence_keys(normalized)
        if evidence_keys:
            risk_summary = "fusion evidence details provided: " + ",".join(evidence_keys)
    if not risk_summary and decision is not None and normalized:
        risk_summary = "fusion response fields provided: " + ",".join(sorted(str(key) for key in normalized))
    if risk_summary:
        normalized["risk_summary"] = str(risk_summary)

    if not normalized.get("fusion_plan_id"):
        normalized["fusion_plan_id"] = plan.fusion_plan_id
    if "required_audit_events" not in normalized:
        normalized["required_audit_events"] = list(plan.required_audit_events)
    allowed = {"fusion_plan_id", "decision_supported", "risk_summary", "required_audit_events"}
    return {key: normalized[key] for key in allowed if key in normalized}


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def _find_bool_by_key(payload: Any, keys: set[str], *, depth: int = 0) -> bool | None:
    if depth > 8:
        return None
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in keys:
                coerced = _coerce_bool(value)
                if coerced is not None:
                    return coerced
        for value in payload.values():
            found = _find_bool_by_key(value, keys, depth=depth + 1)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_bool_by_key(value, keys, depth=depth + 1)
            if found is not None:
                return found
    return None


def _find_text_by_key(payload: Any, keys: set[str], *, depth: int = 0) -> str:
    if depth > 8:
        return ""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in keys and isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = _find_text_by_key(value, keys, depth=depth + 1)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_text_by_key(value, keys, depth=depth + 1)
            if found:
                return found
    return ""


def _find_evidence_keys(payload: Any, *, depth: int = 0) -> list[str]:
    if depth > 8:
        return []
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if isinstance(value, dict) and any(token in lowered for token in ("evidence", "impact", "support")):
                return sorted(str(item_key) for item_key in value)
        for value in payload.values():
            found = _find_evidence_keys(value, depth=depth + 1)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_evidence_keys(value, depth=depth + 1)
            if found:
                return found
    return []


def _exception_summary(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    return {
        "type": type(exc).__name__,
        "message_sha256": stable_hash_payload(message),
        "message_length": len(message),
    }


def _reuse_requirements(node, fact_key: str) -> dict[str, Any]:
    schema_id = ""
    min_confidence = 0.0
    metadata = dict(getattr(node, "metadata", {}) or {})

    schema_map = metadata.get("consumes_fact_schema_ids")
    if isinstance(schema_map, dict):
        schema_id = str(schema_map.get(fact_key) or "")

    confidence_map = metadata.get("consumes_fact_min_confidence")
    if isinstance(confidence_map, dict):
        min_confidence = max(min_confidence, float(confidence_map.get(fact_key) or 0.0))

    for spec in list(metadata.get("consumes_fact_specs") or []):
        if not isinstance(spec, dict):
            continue
        spec_key = str(spec.get("fact_key") or spec.get("key") or "")
        if spec_key != fact_key:
            continue
        schema_id = str(spec.get("schema_id") or schema_id)
        if spec.get("min_confidence") is not None:
            min_confidence = max(min_confidence, float(spec.get("min_confidence") or 0.0))

    for precondition in getattr(node, "preconditions", []) or []:
        if getattr(precondition, "fact_key", "") != fact_key:
            continue
        if getattr(precondition, "required_schema_id", ""):
            schema_id = str(precondition.required_schema_id)
        if getattr(precondition, "min_confidence", None) is not None:
            min_confidence = max(min_confidence, float(precondition.min_confidence or 0.0))

    return {"schema_id": schema_id, "min_confidence": min_confidence}
