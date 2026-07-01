from __future__ import annotations

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.system_call import KernelResponse, LLMQuery
from agentic_os.kernel.system_call.executor import SyscallExecutionResult
from agentic_os.kernel.system_call.models import KernelSyscall
from agentic_os.kernel.scheduler import (
    EdgeType,
    EnvironmentAwareDAGScheduler,
    GoalFusionEngine,
    QueryType,
    ResourceRequest,
    SchedulerAudit,
    TaskGraph,
    TaskGraphStore,
    TaskNode,
    TypedEdge,
)
from agentic_os.kernel.scheduler.environment import EnvironmentFact, EnvironmentStore
from agentic_os.kernel.scheduler.fusion import (
    FusionPlan,
    _fusion_reasoning_prompt,
    _fusion_reasoning_system_prompt,
    _normalize_fusion_reasoning_payload,
)
from agentic_os.kernel.scheduler.global_dag import GlobalGoalDAG
from agentic_os.kernel.scheduler.models import CoverageRequirement, TaskNodeStatus
from agentic_os.kernel.scheduler.opportunity import OpportunityIndex
from agentic_os.kernel.scheduler.preconditions import Precondition


class RecordingFusionLLMKernelService:
    def __init__(self, payload: dict | None = None, *, success: bool = True, error_code: str = "") -> None:
        self.payload = payload or {}
        self.success = success
        self.error_code = error_code
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        payload = self.payload or {
            "fusion_plan_id": str(query.params.get("fusion_plan_id") or ""),
            "decision_supported": True,
            "risk_summary": "verified scheduler fusion explanation",
            "required_audit_events": ["scheduler.fusion.accepted"],
        }
        syscall = KernelSyscall.create(agent_name, "llm", query.operation_type, query.params)
        syscall.syscall_id = "ksc_real_fusion_reasoning"
        syscall.target = "llm"
        response = KernelResponse.ok(payload, metadata={"audit_id": "audit_real_fusion_llm", "model": "real-model"}, data=payload)
        return SyscallExecutionResult(
            syscall=syscall,
            response=response if self.success else KernelResponse.error(self.error_code, metadata={"audit_id": "audit_real_fusion_llm"}),
            success=self.success,
            error_code=self.error_code,
            metadata={"queue_name": "llm", "audit_id": "audit_real_fusion_llm", "model": "real-model"},
        )


def test_fusion_reasoning_normalizes_real_llm_alias_fields_to_schema():
    plan = FusionPlan(
        fusion_plan_id="fusion_alias",
        incoming_graph_id="g_alias",
        base_global_dag_revision=0,
        accepted=True,
        reason="fact_reuse_available",
        required_audit_events=["scheduler.fusion.accepted"],
    )

    normalized = _normalize_fusion_reasoning_payload(
        {
            "supports_existing_plan": True,
            "fusion_reason": "deterministic evidence supports this plan",
            "extra": "ignored after schema projection",
        },
        plan,
    )

    assert normalized == {
        "fusion_plan_id": "fusion_alias",
        "decision_supported": True,
        "risk_summary": "deterministic evidence supports this plan",
        "required_audit_events": ["scheduler.fusion.accepted"],
    }

    evidence_normalized = _normalize_fusion_reasoning_payload(
        {
            "supports_existing_plan": True,
            "evidence_details": {"reuse": "accepted", "coverage": "preserved"},
        },
        plan,
    )
    assert evidence_normalized == {
        "fusion_plan_id": "fusion_alias",
        "decision_supported": True,
        "risk_summary": "fusion evidence details provided: coverage,reuse",
        "required_audit_events": ["scheduler.fusion.accepted"],
    }

    deterministic_evidence_normalized = _normalize_fusion_reasoning_payload(
        {
            "supports_existing_plan": True,
            "deterministic_evidence": {"reuse_edge": "accepted", "source_fact": "verified"},
        },
        plan,
    )
    assert deterministic_evidence_normalized == {
        "fusion_plan_id": "fusion_alias",
        "decision_supported": True,
        "risk_summary": "fusion evidence details provided: reuse_edge,source_fact",
        "required_audit_events": ["scheduler.fusion.accepted"],
    }

    nested_support_normalized = _normalize_fusion_reasoning_payload(
        {
            "supports_plan": True,
            "fusion_evidence": {"accepted": True, "reason": "fact_reuse_available"},
        },
        plan,
    )
    assert nested_support_normalized == {
        "fusion_plan_id": "fusion_alias",
        "decision_supported": True,
        "risk_summary": "fact_reuse_available",
        "required_audit_events": ["scheduler.fusion.accepted"],
    }

    plan_support_normalized = _normalize_fusion_reasoning_payload(
        {
            "plan_support": {"supported": True},
            "fusion_evidence": {"accepted": True},
        },
        plan,
    )
    assert plan_support_normalized["decision_supported"] is True

    recursive_normalized = _normalize_fusion_reasoning_payload(
        {
            "supports_plan": True,
            "reasoning": {
                "deterministic_fusion_evidence": {"fact_reuse": True, "coverage_preservation": True},
            },
        },
        plan,
    )
    assert recursive_normalized == {
        "fusion_plan_id": "fusion_alias",
        "decision_supported": True,
        "risk_summary": "fusion evidence details provided: coverage_preservation,fact_reuse",
        "required_audit_events": ["scheduler.fusion.accepted"],
    }

    string_event_normalized = _normalize_fusion_reasoning_payload(
        {
            "accepted": True,
            "summary": "accepted with one required audit event",
            "required_audit_events": "scheduler.fusion.accepted",
        },
        plan,
    )
    assert string_event_normalized == {
        "fusion_plan_id": "fusion_alias",
        "decision_supported": True,
        "risk_summary": "accepted with one required audit event",
        "required_audit_events": ["scheduler.fusion.accepted"],
    }

    nested_event_normalized = _normalize_fusion_reasoning_payload(
        {
            "reasoning": {
                "plan_id": "fusion_alias",
                "supported_decision": True,
                "risk_summary": "nested response still matches the schema",
                "audit_events": {"events": ["scheduler.fusion.accepted"]},
            }
        },
        plan,
    )
    assert nested_event_normalized == {
        "fusion_plan_id": "fusion_alias",
        "decision_supported": True,
        "risk_summary": "nested response still matches the schema",
        "required_audit_events": ["scheduler.fusion.accepted"],
    }

    text_bool_normalized = _normalize_fusion_reasoning_payload(
        {
            "decision": "supported",
            "summary": "accepted as supported by deterministic evidence",
        },
        plan,
    )
    assert text_bool_normalized["decision_supported"] is True


def test_fusion_reasoning_prompt_uses_schema_valid_top_level_example():
    plan = FusionPlan(
        fusion_plan_id="fusion_prompt",
        incoming_graph_id="g_prompt",
        base_global_dag_revision=0,
        accepted=True,
        reason="fact_reuse_available",
        required_audit_events=["scheduler.fusion.accepted"],
    )
    graph = TaskGraph.create(
        task_graph_id="g_prompt",
        user_goal_id="goal_prompt",
        root_goal="reuse context",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={},
    )
    prompt = _fusion_reasoning_prompt(plan, incoming_graph=graph, global_dag=GlobalGoalDAG())
    system_prompt = _fusion_reasoning_system_prompt()

    assert '"decision_supported": true' in prompt
    assert '"decision_supported": "boolean"' not in prompt
    assert "return_top_level_json_object" in prompt
    assert "Do not wrap the answer inside required_output" in system_prompt


def _global_dag_with_opportunity_window(
    *,
    node_id: str = "inspect_detect",
    workspace_zone: str = "table",
    route_segment_id: str = "route_table",
    resource_id: str = "arm",
) -> tuple[GlobalGoalDAG, OpportunityIndex]:
    inspect_node = TaskNode.create(
        node_id=node_id,
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        workspace_zone=workspace_zone,
        route_segment_id=route_segment_id,
        resources=[ResourceRequest(resource_id=resource_id)] if resource_id else [],
    )
    inspect_graph = TaskGraph.create(
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={node_id: inspect_node},
    )
    global_dag = GlobalGoalDAG()
    global_dag.graphs[inspect_graph.task_graph_id] = inspect_graph
    global_dag.nodes.update(inspect_graph.nodes)
    opportunity_index = OpportunityIndex()
    opportunity_index.rebuild_from_graph(inspect_graph)
    return global_dag, opportunity_index


def test_goal_fusion_rejects_physical_reuse_without_opportunity_window():
    sink = InMemoryKernelEventSink()
    audit = SchedulerAudit(event_sink=sink)
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=30_000_000_000,
        confidence=0.95,
        world_epoch=0,
        schema_id="",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    node = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": node},
    )

    plan = GoalFusionEngine(audit=audit).find_opportunities(
        global_dag=GlobalGoalDAG(),
        incoming_graph=graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
    )

    assert plan.accepted is False
    assert plan.reject_reason == "SCHEDULER_FUSION_OPPORTUNITY_WINDOW_REQUIRED"
    assert plan.blocked_nodes == ["pick"]
    assert plan.reuse_edges[0].accepted is True
    assert plan.resource_impact["opportunity_window_required"] is True
    assert any(
        event["event_type"] == "scheduler.fusion.rejected"
        and event.get("metadata", {}).get("reject_reason") == "SCHEDULER_FUSION_OPPORTUNITY_WINDOW_REQUIRED"
        for event in sink.recent(limit=30)
    )


def test_goal_fusion_accepts_only_verified_reuse_edge_with_safe_opportunity_window():
    sink = InMemoryKernelEventSink()
    audit = SchedulerAudit(event_sink=sink)
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=30_000_000_000,
        confidence=0.95,
        world_epoch=0,
        schema_id="",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    node = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": node},
    )
    global_dag, opportunity_index = _global_dag_with_opportunity_window()

    plan = GoalFusionEngine(audit=audit).find_opportunities(
        global_dag=global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=opportunity_index,
    )

    assert plan.accepted is True
    assert plan.reuse_edges[0].source_real_ok is True
    assert plan.resource_impact["matched_opportunity_window_count"] == 1
    assert plan.coverage_impact["preserved"] is True
    assert any(event["event_type"] == "scheduler.environment.fact_reused" for event in sink.recent(limit=20))
    assert any(event["event_type"] == "scheduler.fusion.coverage_preserved" for event in sink.recent(limit=20))
    assert any(
        event.get("event_type") == "scheduler.fusion.node_inserted"
        and event.get("metadata", {}).get("node_id") == "pick"
        and event.get("metadata", {}).get("fusion_plan_id") == plan.fusion_plan_id
        for event in sink.recent(limit=20)
    )


def test_goal_fusion_rejects_physical_reuse_when_window_lacks_required_resource():
    sink = InMemoryKernelEventSink()
    audit = SchedulerAudit(event_sink=sink)
    environment = EnvironmentStore()
    environment.put(
        EnvironmentFact.create(
            key="cup_pose",
            value={"x": 1.0},
            source_node_id="inspect_detect",
            source_capability="perception.detect_cup",
            source_syscall_id="ksc_real",
            source_audit_id="audit_real",
            source_result={"cup_pose": {"x": 1.0}},
            ttl_ns=30_000_000_000,
            confidence=0.95,
            world_epoch=0,
            schema_id="",
            real_dependency="ros_bridge",
        )
    )
    pick = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": pick},
    )
    global_dag, opportunity_index = _global_dag_with_opportunity_window(resource_id="camera")

    plan = GoalFusionEngine(audit=audit).find_opportunities(
        global_dag=global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=opportunity_index,
    )

    assert plan.accepted is False
    assert plan.reason == "no_safe_resource_window"
    assert plan.reject_reason == "SCHEDULER_FUSION_RESOURCE_WINDOW_UNAVAILABLE"
    assert plan.blocked_nodes == ["pick"]
    assert plan.reuse_edges[0].accepted is True
    assert plan.resource_impact["matched_opportunity_window_count"] == 1
    assert plan.resource_impact["matched_resource_window_count"] == 0
    assert plan.resource_impact["missing_resource_window_ids"] == ["arm"]
    assert plan.resource_impact["resource_window_ok"] is False
    assert plan.audit_metadata["fusion_score_inputs"]["matched_resource_window_count"] == 0
    assert plan.audit_metadata["fusion_score_components"]["resource_contention_penalty"] > 0
    assert any(
        event["event_type"] == "scheduler.fusion.rejected"
        and event.get("metadata", {}).get("reject_reason") == "SCHEDULER_FUSION_RESOURCE_WINDOW_UNAVAILABLE"
        for event in sink.recent(limit=30)
    )


def test_goal_fusion_rejects_window_until_required_precondition_fact_is_verified():
    environment = EnvironmentStore()
    environment.put(
        EnvironmentFact.create(
            key="cup_pose",
            value={"x": 1.0},
            source_node_id="inspect_detect",
            source_capability="perception.detect_cup",
            source_syscall_id="ksc_real_cup",
            source_audit_id="audit_real_cup",
            source_result={"cup_pose": {"x": 1.0}},
            ttl_ns=30_000_000_000,
            confidence=0.95,
            world_epoch=environment.world_epoch,
            schema_id="",
            real_dependency="ros_bridge",
        )
    )
    inspect = TaskNode.create(
        node_id="inspect_detect",
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        workspace_zone="table",
        route_segment_id="route_table",
        resources=[ResourceRequest(resource_id="arm")],
        preconditions=[Precondition("workspace_clear", operator="eq", expected=True)],
    )
    inspect_graph = TaskGraph.create(
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"inspect_detect": inspect},
    )
    global_dag = GlobalGoalDAG()
    global_dag.graphs[inspect_graph.task_graph_id] = inspect_graph
    global_dag.nodes.update(inspect_graph.nodes)
    opportunity_index = OpportunityIndex()
    opportunity_index.rebuild_from_graph(inspect_graph)
    pick = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": pick},
    )

    rejected = GoalFusionEngine().find_opportunities(
        global_dag=global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=opportunity_index,
    )

    assert rejected.accepted is False
    assert rejected.reject_reason == "SCHEDULER_FACT_NOT_FOUND"
    assert rejected.audit_metadata["rejected_opportunity_window_count"] == 1
    assert rejected.audit_metadata["opportunity_window_rejections"][0]["metadata"]["fact_key"] == "workspace_clear"

    environment.put(
        EnvironmentFact.create(
            key="workspace_clear",
            value=True,
            source_node_id="safety_scan",
            source_capability="perception.observe",
            source_syscall_id="ksc_real_clear",
            source_audit_id="audit_real_clear",
            source_result={"workspace_clear": True},
            ttl_ns=30_000_000_000,
            confidence=0.99,
            world_epoch=environment.world_epoch,
            schema_id="",
            real_dependency="ros_bridge",
        )
    )

    accepted = GoalFusionEngine().find_opportunities(
        global_dag=global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=opportunity_index,
    )

    assert accepted.accepted is True
    assert accepted.audit_metadata["rejected_opportunity_window_count"] == 0


def test_opportunity_index_rebuild_replaces_stale_windows_for_graph():
    first = TaskNode.create(
        node_id="inspect",
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        workspace_zone="zone_old",
        route_segment_id="route_old",
    )
    first_graph = TaskGraph.create(
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"inspect": first},
    )
    replacement = TaskNode.create(
        node_id="inspect",
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        workspace_zone="zone_new",
        route_segment_id="route_new",
    )
    replacement_graph = TaskGraph.create(
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"inspect": replacement},
    )
    index = OpportunityIndex()

    index.rebuild_from_graph(first_graph)
    index.rebuild_from_graph(replacement_graph)

    assert index.find(workspace_zone="zone_old", route_segment_id="route_old") == []
    windows = index.find(workspace_zone="zone_new", route_segment_id="route_new")
    assert len(windows) == 1
    assert len(index.snapshot()) == 1


def test_goal_fusion_records_score_formula_components_and_audit_metadata():
    sink = InMemoryKernelEventSink()
    audit = SchedulerAudit(event_sink=sink)
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=30_000_000_000,
        confidence=0.95,
        world_epoch=0,
        schema_id="",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    inspect_node = TaskNode.create(
        node_id="inspect_detect",
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        workspace_zone="zone_a",
        route_segment_id="route_7",
        resources=[ResourceRequest(resource_id="arm")],
    )
    inspect_graph = TaskGraph.create(
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"inspect_detect": inspect_node},
    )
    global_dag = GlobalGoalDAG()
    global_dag.graphs[inspect_graph.task_graph_id] = inspect_graph
    opportunity_index = OpportunityIndex()
    opportunity_index.rebuild_from_graph(inspect_graph)
    pick = TaskNode.create(
        node_id="pick",
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="manipulation.pick_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["cup_pose"],
        workspace_zone="zone_a",
        route_segment_id="route_7",
        resources=[ResourceRequest(resource_id="arm")],
        base_priority=12,
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": pick},
        priority=3,
    )

    plan = GoalFusionEngine(audit=audit).find_opportunities(
        global_dag=global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=opportunity_index,
    )

    components = plan.audit_metadata["fusion_score_components"]
    assert set(components) == {
        "route_overlap_score",
        "fact_reuse_score",
        "resource_window_score",
        "deadline_slack_score",
        "coverage_preservation_score",
        "user_priority_score",
        "safety_risk_penalty",
        "coverage_loss_penalty",
        "resource_contention_penalty",
        "fusion_score",
    }
    assert plan.accepted is True
    assert components["route_overlap_score"] > 0
    assert components["fact_reuse_score"] > 0
    assert components["resource_window_score"] > 0
    assert components["user_priority_score"] > 0
    assert components["safety_risk_penalty"] == 0
    assert components["coverage_loss_penalty"] == 0
    assert components["resource_contention_penalty"] == 0
    assert components["fusion_score"] == (
        components["route_overlap_score"]
        + components["fact_reuse_score"]
        + components["resource_window_score"]
        + components["deadline_slack_score"]
        + components["coverage_preservation_score"]
        + components["user_priority_score"]
        - components["safety_risk_penalty"]
        - components["coverage_loss_penalty"]
        - components["resource_contention_penalty"]
    )
    assert plan.audit_metadata["fusion_score"] == components["fusion_score"]
    assert plan.audit_metadata["fusion_score_inputs"]["matched_resource_window_count"] == 1
    assert any(
        event.get("event_type") == "scheduler.fusion.accepted"
        and event.get("metadata", {}).get("fusion_score") == components["fusion_score"]
        for event in sink.recent(limit=30)
    )


def test_goal_fusion_real_llm_explanation_uses_kernel_service_and_sanitizes_metadata():
    sink, audit, engine, store, environment, graph = _committable_cup_fusion()
    plan = engine.find_opportunities(
        global_dag=store.global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
    )
    service = RecordingFusionLLMKernelService(
        {
            "fusion_plan_id": plan.fusion_plan_id,
            "decision_supported": True,
            "risk_summary": "private LLM reasoning about the user's home",
            "required_audit_events": ["scheduler.fusion.accepted"],
        }
    )

    result = engine.explain_plan_with_real_llm(plan, incoming_graph=graph, global_dag=store.global_dag, kernel_service=service)
    events = sink.recent(limit=40)
    event_text = str(events)
    metadata_text = str(plan.audit_metadata)

    assert result.success is True
    assert isinstance(service.calls[0][1], LLMQuery)
    assert service.calls[0][1].operation_type == "scheduler_explain_fusion_plan"
    assert service.calls[0][1].action_type == "scheduler_planning"
    assert service.calls[0][1].response_format == {"type": "json_object"}
    assert service.calls[0][1].metadata["permissions"] == ["llm.external.call"]
    assert plan.audit_metadata["llm_reasoning"]["status"] == "completed"
    assert plan.audit_metadata["llm_reasoning"]["schema_id"] == "fusion_reasoning.schema.json"
    assert plan.audit_metadata["llm_reasoning"]["syscall_id"] == "ksc_real_fusion_reasoning"
    assert set(plan.audit_metadata["llm_reasoning"]["response_summary"]) == {"sha256", "length", "keys"}
    assert "private LLM reasoning" not in metadata_text
    assert "private LLM reasoning" not in event_text
    assert any(
        event.get("event_type") == "scheduler.llm.real_call_completed"
        and event.get("metadata", {}).get("operation_type") == "scheduler_explain_fusion_plan"
        and event.get("metadata", {}).get("schema_id") == "fusion_reasoning.schema.json"
        for event in events
    )


def test_goal_fusion_real_llm_explanation_returns_stable_unavailable_without_fallback():
    sink, audit, engine, store, environment, graph = _committable_cup_fusion()
    plan = engine.find_opportunities(
        global_dag=store.global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
    )
    service = RecordingFusionLLMKernelService(success=False, error_code="LLM_PROVIDER_UNCONFIGURED")

    result = engine.explain_plan_with_real_llm(plan, incoming_graph=graph, global_dag=store.global_dag, kernel_service=service)
    events = sink.recent(limit=40)

    assert result.success is False
    assert result.error_code == "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED"
    assert result.metadata["upstream_error_code"] == "LLM_PROVIDER_UNCONFIGURED"
    assert plan.audit_metadata["llm_reasoning"]["status"] == "failed"
    assert plan.audit_metadata["llm_reasoning"]["error_code"] == "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED"
    assert any(
        event.get("event_type") == "scheduler.llm.real_call_failed"
        and event.get("metadata", {}).get("operation_type") == "scheduler_explain_fusion_plan"
        and event.get("metadata", {}).get("upstream_error_code") == "LLM_PROVIDER_UNCONFIGURED"
        for event in events
    )


def test_scheduler_submit_graph_triggers_real_llm_fusion_explanation_for_accepted_reuse():
    sink = InMemoryKernelEventSink()
    service = RecordingFusionLLMKernelService()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, kernel_service=service, event_sink=sink)
    producer = TaskNode.create(
        node_id="context_source",
        task_graph_id="context_graph",
        user_goal_id="goal_context",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        produces_facts=["verified_context"],
    )
    producer_graph = TaskGraph.create(
        task_graph_id="context_graph",
        user_goal_id="goal_context",
        root_goal="existing context",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={producer.node_id: producer},
    )
    assert scheduler.submit_graph(producer_graph).success is True
    scheduler.environment_store.put(
        EnvironmentFact.create(
            key="verified_context",
            value={"ok": True},
            source_node_id=producer.node_id,
            source_capability=producer.capability,
            source_syscall_id="ksc_real_context",
            source_audit_id="audit_real_context",
            source_result={"verified_context": {"ok": True}},
            ttl_ns=30_000_000_000,
            confidence=0.99,
            world_epoch=scheduler.environment_store.world_epoch,
            schema_id="",
            real_dependency="real_context_provider",
        )
    )
    consumer = TaskNode.create(
        node_id="context_consumer",
        task_graph_id="consumer_graph",
        user_goal_id="goal_consumer",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        consumes_facts=["verified_context"],
    )
    consumer_graph = TaskGraph.create(
        task_graph_id="consumer_graph",
        user_goal_id="goal_consumer",
        root_goal="reuse context",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={consumer.node_id: consumer},
    )

    response = scheduler.submit_graph(consumer_graph)
    plan = scheduler.fusion_engine.snapshot()[-1]

    assert response.success is True
    assert service.calls[0][1].operation_type == "scheduler_explain_fusion_plan"
    assert service.calls[0][1].response_format == {"type": "json_object"}
    assert service.calls[0][1].metadata["permissions"] == ["llm.external.call"]
    assert plan["audit_metadata"]["llm_reasoning"]["status"] == "completed"
    assert any(
        event.get("event_type") == "scheduler.llm.real_call_completed"
        and event.get("metadata", {}).get("operation_type") == "scheduler_explain_fusion_plan"
        for event in sink.recent(limit=80)
    )


def test_scheduler_submit_graph_rejects_accepted_fusion_when_real_llm_explanation_fails():
    sink = InMemoryKernelEventSink()
    service = RecordingFusionLLMKernelService(success=False, error_code="LLM_PROVIDER_UNCONFIGURED")
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, kernel_service=service, event_sink=sink)
    producer = TaskNode.create(
        node_id="context_source",
        task_graph_id="context_graph",
        user_goal_id="goal_context",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        produces_facts=["verified_context"],
    )
    producer_graph = TaskGraph.create(
        task_graph_id="context_graph",
        user_goal_id="goal_context",
        root_goal="existing context",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={producer.node_id: producer},
    )
    assert scheduler.submit_graph(producer_graph).success is True
    scheduler.environment_store.put(
        EnvironmentFact.create(
            key="verified_context",
            value={"ok": True},
            source_node_id=producer.node_id,
            source_capability=producer.capability,
            source_syscall_id="ksc_real_context",
            source_audit_id="audit_real_context",
            source_result={"verified_context": {"ok": True}},
            ttl_ns=30_000_000_000,
            confidence=0.99,
            world_epoch=scheduler.environment_store.world_epoch,
            schema_id="",
            real_dependency="real_context_provider",
        )
    )
    consumer = TaskNode.create(
        node_id="context_consumer",
        task_graph_id="consumer_graph",
        user_goal_id="goal_consumer",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        consumes_facts=["verified_context"],
    )
    consumer_graph = TaskGraph.create(
        task_graph_id="consumer_graph",
        user_goal_id="goal_consumer",
        root_goal="reuse context",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={consumer.node_id: consumer},
    )

    response = scheduler.submit_graph(consumer_graph)
    events = sink.recent(limit=100)

    assert response.success is False
    assert response.error_code == "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED"
    assert response.metadata["upstream_error_code"] == "LLM_PROVIDER_UNCONFIGURED"
    assert "consumer_graph" not in scheduler.graph_store.global_dag.graphs
    assert any(
        event.get("event_type") == "scheduler.llm.real_call_failed"
        and event.get("metadata", {}).get("operation_type") == "scheduler_explain_fusion_plan"
        for event in events
    )
    assert any(
        event.get("event_type") == "scheduler.graph.rejected"
        and event.get("metadata", {}).get("error_code") == "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED"
        and event.get("metadata", {}).get("upstream_error_code") == "LLM_PROVIDER_UNCONFIGURED"
        for event in events
    )


def test_scheduler_submit_graph_rejects_accepted_fusion_when_llm_reasoning_plan_id_mismatches():
    sink = InMemoryKernelEventSink()
    service = RecordingFusionLLMKernelService(
        {
            "fusion_plan_id": "different_fusion_plan",
            "decision_supported": True,
            "risk_summary": "claims to support a different fusion plan",
            "required_audit_events": ["scheduler.fusion.accepted"],
        }
    )
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, kernel_service=service, event_sink=sink)
    producer = TaskNode.create(
        node_id="context_source",
        task_graph_id="context_graph",
        user_goal_id="goal_context",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        produces_facts=["verified_context"],
    )
    producer_graph = TaskGraph.create(
        task_graph_id="context_graph",
        user_goal_id="goal_context",
        root_goal="existing context",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={producer.node_id: producer},
    )
    assert scheduler.submit_graph(producer_graph).success is True
    scheduler.environment_store.put(
        EnvironmentFact.create(
            key="verified_context",
            value={"ok": True},
            source_node_id=producer.node_id,
            source_capability=producer.capability,
            source_syscall_id="ksc_real_context",
            source_audit_id="audit_real_context",
            source_result={"verified_context": {"ok": True}},
            ttl_ns=30_000_000_000,
            confidence=0.99,
            world_epoch=scheduler.environment_store.world_epoch,
            schema_id="",
            real_dependency="real_context_provider",
        )
    )
    consumer = TaskNode.create(
        node_id="context_consumer",
        task_graph_id="consumer_graph",
        user_goal_id="goal_consumer",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        consumes_facts=["verified_context"],
    )
    consumer_graph = TaskGraph.create(
        task_graph_id="consumer_graph",
        user_goal_id="goal_consumer",
        root_goal="reuse context",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={consumer.node_id: consumer},
    )

    response = scheduler.submit_graph(consumer_graph)
    events = sink.recent(limit=100)

    assert response.success is False
    assert response.error_code == "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID"
    assert "consumer_graph" not in scheduler.graph_store.global_dag.graphs
    assert any(
        event.get("event_type") == "scheduler.llm.real_call_failed"
        and event.get("metadata", {}).get("error_code") == "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID"
        for event in events
    )
    assert any(
        event.get("event_type") == "scheduler.graph.rejected"
        and event.get("metadata", {}).get("error_code") == "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID"
        for event in events
    )


def test_goal_fusion_score_penalizes_unverified_reuse_risk_and_contention():
    pick = TaskNode.create(
        node_id="pick",
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="manipulation.pick_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["cup_pose"],
        resources=[ResourceRequest(resource_id="arm", mode="exclusive")],
        safety_class="collision_risk",
        safety_constraints={"requires_clear_workspace": True},
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": pick},
    )

    plan = GoalFusionEngine().find_opportunities(
        global_dag=GlobalGoalDAG(),
        incoming_graph=graph,
        environment=EnvironmentStore(),
        opportunity_index=OpportunityIndex(),
    )

    components = plan.audit_metadata["fusion_score_components"]
    assert plan.accepted is False
    assert components["fact_reuse_score"] == 0
    assert components["resource_window_score"] == 0
    assert components["resource_contention_penalty"] > 0
    assert components["safety_risk_penalty"] > 0
    assert components["fusion_score"] < components["coverage_preservation_score"]


def test_goal_fusion_rejects_missing_verified_fact():
    node = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": node},
    )

    plan = GoalFusionEngine().find_opportunities(
        global_dag=GlobalGoalDAG(),
        incoming_graph=graph,
        environment=EnvironmentStore(),
        opportunity_index=OpportunityIndex(),
    )

    assert plan.accepted is False
    assert plan.reject_reason == "SCHEDULER_FACT_NOT_FOUND"
    assert plan.blocked_nodes == ["pick"]


def test_goal_fusion_emits_stale_reuse_rejected_for_expired_fact():
    sink = InMemoryKernelEventSink()
    audit = SchedulerAudit(event_sink=sink)
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=1,
        confidence=0.95,
        world_epoch=0,
        schema_id="",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    environment.expire(fact.timestamp_ns + 2)
    node = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": node},
    )

    plan = GoalFusionEngine(audit=audit).find_opportunities(
        global_dag=GlobalGoalDAG(),
        incoming_graph=graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
    )

    assert plan.accepted is False
    assert plan.reject_reason == "SCHEDULER_REUSE_TTL_OK_FAILED"
    assert plan.reuse_edges[0].ttl_ok is False
    assert plan.reuse_edges[0].fact_id == fact.fact_id
    assert any(
        event.get("event_type") == "scheduler.fusion.stale_reuse_rejected"
        and event.get("metadata", {}).get("fact_id") == fact.fact_id
        for event in sink.recent(limit=20)
    )


def test_goal_fusion_uses_fact_schema_not_capability_input_schema_for_reuse():
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=30_000_000_000,
        confidence=0.91,
        world_epoch=0,
        schema_id="cup_pose.schema.json",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    node = TaskNode.create(
        node_id="pick",
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="manipulation.pick_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        input_schema_id="capability:manipulation.pick_cup:input",
        consumes_facts=["cup_pose"],
        workspace_zone="table",
        route_segment_id="route_table",
        resources=[ResourceRequest(resource_id="arm")],
        metadata={"consumes_fact_schema_ids": {"cup_pose": "cup_pose.schema.json"}},
        preconditions=[Precondition("cup_pose", min_confidence=0.9, required_schema_id="cup_pose.schema.json")],
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": node},
    )
    global_dag, opportunity_index = _global_dag_with_opportunity_window()

    plan = GoalFusionEngine().find_opportunities(
        global_dag=global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=opportunity_index,
    )

    assert plan.accepted is True
    assert plan.reuse_edges[0].schema_ok is True


def test_goal_fusion_rejects_reuse_when_required_fact_schema_mismatches():
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=30_000_000_000,
        confidence=0.95,
        world_epoch=0,
        schema_id="other_pose.schema.json",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    node = TaskNode.create(
        node_id="pick",
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="manipulation.pick_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["cup_pose"],
        metadata={"consumes_fact_specs": [{"fact_key": "cup_pose", "schema_id": "cup_pose.schema.json", "min_confidence": 0.9}]},
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": node},
    )

    plan = GoalFusionEngine().find_opportunities(
        global_dag=GlobalGoalDAG(),
        incoming_graph=graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
    )

    assert plan.accepted is False
    assert plan.reuse_edges[0].schema_ok is False
    assert plan.reuse_edges[0].reject_reason == "SCHEDULER_REUSE_SCHEMA_OK_FAILED"


def test_goal_fusion_records_per_requirement_coverage_impact():
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=30_000_000_000,
        confidence=0.95,
        world_epoch=0,
        schema_id="",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    inspect_node = TaskNode.create(
        node_id="inspect_detect",
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        workspace_zone="zone_a",
        route_segment_id="route_a",
        resources=[ResourceRequest(resource_id="arm")],
    )
    existing_graph = TaskGraph.create(
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"inspect_detect": inspect_node},
        coverage_requirements=[
            CoverageRequirement(requirement_id="zone_a", workspace_zone="zone_a"),
            CoverageRequirement(requirement_id="zone_b", workspace_zone="zone_b"),
        ],
    )
    global_dag = GlobalGoalDAG()
    global_dag.graphs[existing_graph.task_graph_id] = existing_graph
    global_dag.nodes.update(existing_graph.nodes)
    node = TaskNode.create(
        node_id="pick",
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="manipulation.pick_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["cup_pose"],
        workspace_zone="zone_a",
        route_segment_id="route_a",
        resources=[ResourceRequest(resource_id="arm")],
    )
    cup_graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": node},
    )

    plan = GoalFusionEngine().find_opportunities(
        global_dag=global_dag,
        incoming_graph=cup_graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
    )

    impacts = plan.coverage_impact["requirements"]
    assert plan.accepted is True
    assert plan.coverage_impact["preserved"] is True
    assert [impact["before"]["requirement_id"] for impact in impacts] == ["zone_a", "zone_b"]
    assert [impact["after"]["requirement_id"] for impact in impacts] == ["zone_a", "zone_b"]
    assert all(impact["preserved"] for impact in impacts)


def test_goal_fusion_commit_adds_reuse_edge_after_two_phase_validation():
    sink, audit, engine, store, environment, graph = _committable_cup_fusion()
    plan = engine.find_opportunities(
        global_dag=store.global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
    )

    result = engine.commit_fusion(store, graph, plan)

    assert result.success is True
    stored = store.get_graph("cup_graph")
    reuse_edges = [edge for edge in stored.edges if edge.edge_type == EdgeType.REUSES_FACT]
    assert reuse_edges[0].source_id == "inspect_detect"
    assert reuse_edges[0].target_id == "pick"
    assert reuse_edges[0].fact_key == "cup_pose"
    insertion_edges = [
        edge
        for edge in stored.edges
        if edge.edge_type == EdgeType.PRECEDENCE
        and edge.source_id == "inspect_detect"
        and edge.target_id == "pick"
        and edge.metadata.get("fusion_plan_id") == plan.fusion_plan_id
    ]
    assert insertion_edges
    assert insertion_edges[0].metadata["cross_graph_dependency"] is True
    assert stored.nodes["pick"].dependencies == {"inspect_detect"}
    assert store.global_dag.reverse_edges["pick"] == {"inspect_detect"}
    assert any(
        event.get("event_type") == "scheduler.fusion.commit_accepted"
        and event.get("metadata", {}).get("fusion_plan_id") == plan.fusion_plan_id
        for event in sink.recent(limit=30)
    )
    assert audit.recent_ids()


def test_scheduler_fused_node_waits_for_cross_graph_insertion_anchor():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, event_sink=sink)
    inspect = TaskNode.create(
        node_id="inspect_detect",
        task_graph_id="inspect_graph",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    inspect_graph = TaskGraph.create(
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"inspect_detect": inspect},
    )
    assert scheduler.submit_graph(inspect_graph).success is True
    scheduler.environment_store.put(
        EnvironmentFact.create(
            key="cup_pose",
            value={"x": 1.0},
            source_node_id="inspect_detect",
            source_capability="perception.detect_cup",
            source_syscall_id="ksc_real",
            source_audit_id="audit_real",
            source_result={"cup_pose": {"x": 1.0}},
            ttl_ns=30_000_000_000,
            confidence=0.95,
            world_epoch=0,
            schema_id="",
            real_dependency="ros_bridge",
        )
    )
    pick = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    cup_graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": pick},
    )

    assert scheduler.submit_graph(cup_graph).success is True

    stored_pick = scheduler.graph_store.get_node("pick")
    assert stored_pick.dependencies == {"inspect_detect"}
    assert stored_pick.status == TaskNodeStatus.WAITING
    assert "pick" not in {item["node_id"] for item in scheduler.ready_queue.snapshot()}

    scheduler.graph_store.mark_status("inspect_detect", TaskNodeStatus.COMPLETED)
    scheduler.refresh_ready_nodes()

    assert scheduler.graph_store.get_node("pick").status == TaskNodeStatus.READY
    assert "pick" in {item["node_id"] for item in scheduler.ready_queue.snapshot()}


def test_scheduler_fusion_window_blocks_existing_successor_until_inserted_node_completes():
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {})
    detect = TaskNode.create(
        node_id="detect_cup",
        task_graph_id="inspect_graph",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    next_inspect = TaskNode.create(
        node_id="navigate_zone_b",
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
    )
    inspect_graph = TaskGraph.create(
        task_graph_id="inspect_graph",
        user_goal_id="goal_inspect",
        root_goal="inspect",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"detect_cup": detect, "navigate_zone_b": next_inspect},
        edges=[TypedEdge("detect_then_zone_b", "detect_cup", "navigate_zone_b", EdgeType.PRECEDENCE)],
    )
    assert scheduler.submit_graph(inspect_graph).success is True
    scheduler.graph_store.mark_status("detect_cup", TaskNodeStatus.COMPLETED)
    scheduler.refresh_ready_nodes()
    assert scheduler.graph_store.get_node("navigate_zone_b").status == TaskNodeStatus.READY

    scheduler.environment_store.put(
        EnvironmentFact.create(
            key="cup_pose",
            value={"x": 1.0},
            source_node_id="detect_cup",
            source_capability="perception.detect_cup",
            source_syscall_id="ksc_real",
            source_audit_id="audit_real",
            source_result={"cup_pose": {"x": 1.0}},
            ttl_ns=30_000_000_000,
            confidence=0.95,
            world_epoch=0,
            schema_id="",
            real_dependency="ros_bridge",
        )
    )
    pick = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    cup_graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": pick},
    )

    response = scheduler.submit_graph(cup_graph)
    plan = scheduler.fusion_engine.snapshot()[-1]

    assert response.success is True
    assert plan["accepted"] is True
    assert plan["insertions"][0]["after_node_id"] == "detect_cup"
    assert plan["insertions"][0]["before_node_id"] == "navigate_zone_b"
    stored = scheduler.graph_store.get_graph("cup_graph")
    assert any(
        edge.edge_type == EdgeType.PRECEDENCE
        and edge.source_id == "pick"
        and edge.target_id == "navigate_zone_b"
        and edge.metadata.get("cross_graph_dependency") is True
        for edge in stored.edges
    )
    assert scheduler.graph_store.get_node("pick").status == TaskNodeStatus.READY
    assert scheduler.graph_store.get_node("navigate_zone_b").status == TaskNodeStatus.WAITING
    assert "navigate_zone_b" not in {item["node_id"] for item in scheduler.ready_queue.snapshot()}

    scheduler.graph_store.mark_status("pick", TaskNodeStatus.COMPLETED)
    scheduler.refresh_ready_nodes()

    assert scheduler.graph_store.get_node("navigate_zone_b").status == TaskNodeStatus.READY


def test_goal_fusion_commit_rejects_reuse_edge_with_producer_outside_global_dag():
    sink = InMemoryKernelEventSink()
    audit = SchedulerAudit(event_sink=sink)
    engine = GoalFusionEngine(audit=audit)
    store = TaskGraphStore()
    window_anchor = TaskNode.create(
        node_id="window_anchor",
        task_graph_id="window_graph",
        user_goal_id="goal_window",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        workspace_zone="table",
        route_segment_id="route_table",
        resources=[ResourceRequest(resource_id="arm")],
    )
    window_graph = TaskGraph.create(
        task_graph_id="window_graph",
        user_goal_id="goal_window",
        root_goal="window",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"window_anchor": window_anchor},
    )
    store.add_graph(window_graph)
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="external_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=30_000_000_000,
        confidence=0.95,
        world_epoch=0,
        schema_id="",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    pick = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": pick},
    )
    opportunity_index = OpportunityIndex()
    opportunity_index.rebuild_from_graph(window_graph)
    plan = engine.find_opportunities(
        global_dag=store.global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=opportunity_index,
    )

    result = engine.commit_fusion(store, graph, plan)

    assert plan.accepted is True
    assert result.success is False
    assert result.error_code == "SCHEDULER_FUSION_REUSE_PRODUCER_NOT_IN_DAG"
    assert "cup_graph" not in store.global_dag.graphs
    assert any(
        event.get("event_type") == "scheduler.fusion.commit_rejected"
        and event.get("metadata", {}).get("error_code") == "SCHEDULER_FUSION_REUSE_PRODUCER_NOT_IN_DAG"
        for event in sink.recent(limit=40)
    )


def test_goal_fusion_commit_rejects_revision_conflict_without_mutating_graph_store():
    sink, _audit, engine, store, environment, graph = _committable_cup_fusion()
    plan = engine.find_opportunities(
        global_dag=store.global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
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
    store.add_graph(
        TaskGraph.create(
            task_graph_id="other_graph",
            user_goal_id="other_goal",
            root_goal="other",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            nodes={"other": other},
        )
    )

    result = engine.commit_fusion(store, graph, plan)

    assert result.success is False
    assert result.error_code == "SCHEDULER_FUSION_REBASE_REQUIRED"
    assert result.retry_required is True
    assert result.metadata["legacy_error_code"] == "SCHEDULER_FUSION_REVISION_CONFLICT"
    assert "cup_graph" not in store.global_dag.graphs
    assert any(
        event.get("event_type") == "scheduler.fusion.commit_rejected"
        and event.get("metadata", {}).get("error_code") == "SCHEDULER_FUSION_REBASE_REQUIRED"
        and event.get("metadata", {}).get("legacy_error_code") == "SCHEDULER_FUSION_REVISION_CONFLICT"
        for event in sink.recent(limit=30)
    )


def test_goal_fusion_commit_rejects_expired_deadline_before_mutating_graph_store():
    _sink, _audit, engine, store, environment, graph = _committable_cup_fusion(deadline_ns=1)
    plan = engine.find_opportunities(
        global_dag=store.global_dag,
        incoming_graph=graph,
        environment=environment,
        opportunity_index=OpportunityIndex(),
    )

    result = engine.commit_fusion(store, graph, plan)

    assert result.success is False
    assert result.error_code == "SCHEDULER_FUSION_DEADLINE_INVALID"
    assert "cup_graph" not in store.global_dag.graphs


def _committable_cup_fusion(*, deadline_ns=None):
    sink = InMemoryKernelEventSink()
    audit = SchedulerAudit(event_sink=sink)
    engine = GoalFusionEngine(audit=audit)
    store = TaskGraphStore()
    producer = TaskNode.create(
        node_id="inspect_detect",
        task_graph_id="inspect_graph",
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
        resources=[ResourceRequest(resource_id="arm")],
    )
    store.add_graph(
        TaskGraph.create(
            task_graph_id="inspect_graph",
            user_goal_id="goal_inspect",
            root_goal="inspect",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            nodes={"inspect_detect": producer},
            coverage_requirements=[CoverageRequirement(requirement_id="zone_a", workspace_zone="zone_a")],
        )
    )
    environment = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect_detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=30_000_000_000,
        confidence=0.95,
        world_epoch=0,
        schema_id="",
        real_dependency="ros_bridge",
    )
    environment.put(fact)
    pick = TaskNode.create(
        node_id="pick",
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
        resources=[ResourceRequest(resource_id="arm")],
        deadline_ns=deadline_ns,
    )
    graph = TaskGraph.create(
        task_graph_id="cup_graph",
        user_goal_id="goal_cup",
        root_goal="bring cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": pick},
    )
    return sink, audit, engine, store, environment, graph
