from __future__ import annotations

import json

import pytest

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.system_call import KernelResponse
from agentic_os.kernel.system_call.executor import SyscallExecutionResult
from agentic_os.kernel.system_call.models import KernelSyscall
from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, QueryType, SchedulerAudit, SchedulerError, TaskGraph, TaskGraphPlanner, TaskNode
from agentic_os.kernel.scheduler.admission import AdmissionController
from agentic_os.kernel.scheduler.task_graph_planner import (
    extract_llm_json_object,
    _build_goal_prompt,
    _complete_authoritative_graph_envelope,
    _validate_planner_identity,
)
from agentic_runtime.kernel_service import KernelService


class Config:
    scheduler_policy = "fifo"
    storage_root = "/tmp/agentic_scheduler_llm"
    kernel = {"scheduler_policy": "env_aware_priority_dag"}


class RaisingPlanningKernelService:
    def __init__(self) -> None:
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        raise RuntimeError("api_key=secret-value prompt=private planning prompt")


class SchemaDriftPlanningKernelService:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        syscall = KernelSyscall.create(agent_name, "llm", query.operation_type, query.params)
        syscall.syscall_id = "ksc_schema_drift_plan"
        syscall.target = "llm"
        response = KernelResponse.ok(self.payload, metadata={"audit_id": "audit_real_planner", "model": "real-model"}, data=self.payload)
        return SyscallExecutionResult(
            syscall=syscall,
            response=response,
            success=True,
            metadata={"queue_name": "llm", "audit_id": "audit_real_planner", "model": "real-model"},
        )


def test_submit_goal_requires_real_llm_provider_without_planner_fallback():
    service = KernelService(config=Config())
    agent = service.create_agent(app_id="app", session_id="sess", agent_id="agent_llm")
    service.start_agent(agent.agent_id)

    response = service.scheduler.submit_goal("create a safe report graph", agent_id=agent.agent_id, app_id="app", session_id="sess")

    assert response.success is False
    assert response.error_code == "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED"
    events = service.event_sink.recent(limit=50)
    submitted_events = [event for event in events if event["event_type"] == "scheduler.goal.submitted"]
    failed_events = [event for event in events if event["event_type"] == "scheduler.llm.real_call_failed"]
    started_events = [event for event in events if event["event_type"] == "scheduler.llm.real_call_started"]
    goal_id = submitted_events[0]["metadata"]["goal_id"]
    assert goal_id.startswith("goal_")
    assert response.metadata["goal_id"] == goal_id
    assert started_events[0]["metadata"]["operation_type"] == "scheduler_generate_task_graph"
    assert started_events[0]["metadata"]["schema_id"] == "task_graph.schema.json"
    assert started_events[0]["metadata"]["goal_id"] == goal_id
    assert failed_events[0]["metadata"]["goal_id"] == goal_id
    assert failed_events[0]["metadata"]["syscall_id"].startswith("ksc_")
    assert failed_events[0]["metadata"]["upstream_error_code"]
    service.stop()


def test_planner_validates_raw_resource_schema_before_model_coercion():
    sink = InMemoryKernelEventSink()
    payload = _planner_payload()
    payload["nodes"]["report"]["resources"] = [
        {
            "resource_id": "status_panel",
            "mode": "shared",
            "amount": "2",
            "lease_ttl_ns": 100_000_000,
            "priority_ceiling": 5,
        }
    ]
    kernel_service = SchemaDriftPlanningKernelService(payload)
    planner = TaskGraphPlanner(
        kernel_service=kernel_service,
        admission=AdmissionController(),
        audit=SchedulerAudit(event_sink=sink),
    )

    with pytest.raises(SchedulerError) as error:
        planner.generate_task_graph(
            "create a safe report graph",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            user_goal_id="goal_expected",
        )

    events = sink.recent(limit=20)
    assert error.value.error_code == "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID"
    assert error.value.metadata["syscall_id"] == "ksc_schema_drift_plan"
    assert kernel_service.calls[0][1].response_format == {"type": "json_object"}
    assert kernel_service.calls[0][1].metadata["permissions"] == ["llm.external.call"]
    assert any(
        event["event_type"] == "scheduler.llm.real_call_failed"
        and event["metadata"]["error_code"] == "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID"
        and event["metadata"]["syscall_id"] == "ksc_schema_drift_plan"
        for event in events
    )
    assert not any(event["event_type"] == "scheduler.llm.real_call_completed" for event in events)


def test_planner_rejects_llm_candidate_that_claims_physical_fact_output():
    sink = InMemoryKernelEventSink()
    payload = _planner_payload()
    payload["nodes"]["report"]["query_type"] = QueryType.LLM
    payload["nodes"]["report"]["capability"] = "llm.plan"
    payload["nodes"]["report"]["operation_type"] = "chat"
    payload["nodes"]["report"]["produces_facts"] = ["cup_pose"]
    kernel_service = SchemaDriftPlanningKernelService(payload)
    planner = TaskGraphPlanner(
        kernel_service=kernel_service,
        admission=AdmissionController(),
        audit=SchedulerAudit(event_sink=sink),
    )

    with pytest.raises(SchedulerError) as error:
        planner.generate_task_graph(
            "create a safe report graph",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            user_goal_id="goal_expected",
        )

    events = sink.recent(limit=20)
    assert error.value.error_code == "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID"
    assert "SCHEDULER_FACT_SOURCE_UNVERIFIED" in error.value.message
    assert any(
        event["event_type"] == "scheduler.llm.real_call_failed"
        and event["metadata"]["error_code"] == "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID"
        and event["metadata"]["syscall_id"] == "ksc_schema_drift_plan"
        for event in events
    )
    assert not any(event["event_type"] == "scheduler.llm.real_call_completed" for event in events)


def test_planner_extracts_task_graph_wrapped_real_llm_json_candidate():
    candidate = _planner_payload()

    assert extract_llm_json_object({"task_graph": candidate}) == candidate
    assert extract_llm_json_object({"graph": candidate}) == candidate
    assert extract_llm_json_object({"taskGraph": candidate}) == candidate
    assert extract_llm_json_object({"data": {"task_graph": candidate}}) == candidate
    assert extract_llm_json_object({"response": {"content": json.dumps({"graph": candidate})}}) == candidate
    assert extract_llm_json_object({"fusion_reasoning": {"decision_supported": True}}) == {"decision_supported": True}


def test_goal_prompt_names_required_top_level_task_graph_fields():
    prompt = json.loads(
        _build_goal_prompt(
            "create a safe report graph",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            user_goal_id="goal_expected",
        )
    )

    assert prompt["strict_top_level_required_keys"] == [
        "task_graph_id",
        "user_goal_id",
        "agent_id",
        "app_id",
        "session_id",
        "root_goal",
        "nodes",
        "edges",
        "status",
    ]
    assert prompt["minimal_valid_example_for_safe_report_goal"]["root_goal"] == "create a safe report graph"
    assert prompt["minimal_valid_example_for_safe_report_goal"]["nodes"]["report"]["capability"] == "report.say"


def test_planner_overrides_authoritative_graph_envelope_fields():
    payload = _planner_payload()
    payload.pop("root_goal")
    payload.pop("status")

    completed = _complete_authoritative_graph_envelope(
        payload,
        goal="create a safe report graph",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        user_goal_id="goal_expected",
    )

    assert completed["root_goal"] == "create a safe report graph"
    assert completed["status"] == "created"
    assert completed["agent_id"] == "agent"
    assert completed["task_graph_id"].startswith("graph_")
    assert completed["task_graph_id"] != payload["task_graph_id"]
    assert completed["nodes"]["report"]["node_id"] == "report"
    assert completed["nodes"]["report"]["task_graph_id"] == completed["task_graph_id"]
    assert completed["nodes"]["report"]["agent_id"] == "agent"
    mismatched = _complete_authoritative_graph_envelope(
        {"root_goal": "changed by model", "status": "running"},
        goal="create a safe report graph",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        user_goal_id="goal_expected",
    )
    assert mismatched["root_goal"] == "create a safe report graph"
    assert mismatched["status"] == "created"


def test_planner_canonicalizes_real_llm_nodes_list_and_edge_aliases():
    payload = _planner_payload()
    report_node = dict(payload["nodes"]["report"])
    report_node.pop("node_id")
    report_node["id"] = "report"
    payload["nodes"] = [report_node]
    payload["edges"] = [{"source": "report", "target": "report"}]

    completed = _complete_authoritative_graph_envelope(
        payload,
        goal="create a safe report graph",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        user_goal_id="goal_expected",
    )

    assert sorted(completed["nodes"]) == ["report"]
    assert completed["nodes"]["report"]["node_id"] == "report"
    assert completed["edges"][0]["source_id"] == "report"
    assert completed["edges"][0]["target_id"] == "report"
    assert completed["edges"][0]["edge_type"] == "precedence"


def test_planner_canonicalizes_real_llm_task_aliases_and_node_field_aliases():
    payload = {
        "tasks": [
            {
                "id": "report",
                "skill": "report.say",
                "query_type": "SKILL",
                "message": "scheduler verification complete",
                "resources": ["status_panel"],
                "required_permissions": "report.write",
            }
        ],
        "edges": [],
    }

    completed = _complete_authoritative_graph_envelope(
        payload,
        goal="create a safe report graph",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        user_goal_id="goal_expected",
    )

    node = completed["nodes"]["report"]
    assert node["node_id"] == "report"
    assert node["task_graph_id"] == completed["task_graph_id"]
    assert node["user_goal_id"] == "goal_expected"
    assert node["agent_id"] == "agent"
    assert node["agent_name"] == "app"
    assert node["app_id"] == "app"
    assert node["session_id"] == "sess"
    assert node["capability"] == "report.say"
    assert node["operation_type"] == "skill_call"
    assert node["query_type"] == "skill"
    assert node["status"] == "created"
    assert node["params"] == {"message": "scheduler verification complete"}
    assert node["metadata"] == {}
    assert node["dependencies"] == []
    assert node["dependents"] == []
    assert node["resources"] == [{"resource_id": "status_panel"}]
    assert node["required_permissions"] == ["report.write"]
    assert node["safety_constraints"] == {}
    assert node["produces_facts"] == []
    assert node["consumes_facts"] == []
    assert node["resource_lease_ids"] == []
    assert node["audit_ids"] == []


def test_planner_canonicalizes_single_top_level_node_payload_from_real_llm():
    payload = {
        "id": "report",
        "action": "report.say",
        "type": "skill_call",
        "text": "scheduler verification complete",
    }

    completed = _complete_authoritative_graph_envelope(
        payload,
        goal="create a safe report graph",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        user_goal_id="goal_expected",
    )

    assert sorted(completed["nodes"]) == ["report"]
    node = completed["nodes"]["report"]
    assert node["capability"] == "report.say"
    assert node["operation_type"] == "skill_call"
    assert node["query_type"] == "skill"
    assert node["params"] == {"message": "scheduler verification complete"}


def test_submit_goal_returns_stable_llm_error_when_planning_execute_request_raises_without_leaking_prompt():
    sink = InMemoryKernelEventSink()
    kernel_service = RaisingPlanningKernelService()
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(event_sink=sink),
        {},
        kernel_service=kernel_service,
        event_sink=sink,
    )

    response = scheduler.submit_goal(
        "private user goal",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        agent_name="agent_app",
    )
    events = sink.recent(limit=20)
    events_text = str(events)

    assert response.success is False
    assert response.error_code == "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED"
    assert response.metadata["upstream_error_code"] == "SCHEDULER_DISPATCH_FAILED"
    assert response.metadata["exception"]["type"] == "RuntimeError"
    assert set(response.metadata["exception"]) == {"type", "message_sha256", "message_length"}
    assert kernel_service.calls[0][0] == "agent_app"
    assert "secret-value" not in str(response.metadata)
    assert "private planning prompt" not in str(response.metadata)
    assert "private user goal" not in events_text
    assert "secret-value" not in events_text
    assert "private planning prompt" not in events_text
    assert any(
        event["event_type"] == "scheduler.llm.real_call_failed"
        and event["metadata"]["error_code"] == "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED"
        and event["metadata"]["upstream_error_code"] == "SCHEDULER_DISPATCH_FAILED"
        and event["metadata"]["exception"]["type"] == "RuntimeError"
        for event in events
    )


def test_planner_identity_validator_rejects_rewritten_root_goal():
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="rewritten goal",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={
            "report": TaskNode.create(
                node_id="report",
                task_graph_id="g",
                user_goal_id="goal",
                agent_id="agent",
                agent_name="app",
                app_id="app",
                session_id="sess",
                capability="report.say",
                query_type=QueryType.SKILL,
                params={"message": "done"},
            )
        },
    )

    with pytest.raises(ValueError, match="planner graph identifiers changed"):
        _validate_planner_identity(
            graph,
            goal="original goal",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            admission=AdmissionController(),
        )


def test_planner_identity_validator_rejects_goal_id_drift():
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal_from_provider",
        root_goal="original goal",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={
            "report": TaskNode.create(
                node_id="report",
                task_graph_id="g",
                user_goal_id="goal_from_provider",
                agent_id="agent",
                agent_name="app",
                app_id="app",
                session_id="sess",
                capability="report.say",
                query_type=QueryType.SKILL,
                params={"message": "done"},
            )
        },
    )

    with pytest.raises(ValueError, match="planner graph identifiers changed"):
        _validate_planner_identity(
            graph,
            goal="original goal",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            admission=AdmissionController(),
            user_goal_id="goal_expected",
        )


def test_planner_prompt_pins_scheduler_goal_id_contract():
    payload = json.loads(
        _build_goal_prompt(
            "original goal",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            user_goal_id="goal_expected",
        )
    )

    assert payload["required_identifiers"]["user_goal_id"] == "goal_expected"
    assert payload["output_contract"]["user_goal_id"] == "goal_expected"
    assert payload["output_contract"]["nodes"]["node_id"]["user_goal_id"] == "goal_expected"


def _planner_payload() -> dict:
    return {
        "task_graph_id": "g_planner_schema",
        "user_goal_id": "goal_expected",
        "agent_id": "agent",
        "app_id": "app",
        "session_id": "sess",
        "root_goal": "create a safe report graph",
        "nodes": {
            "report": {
                "node_id": "report",
                "task_graph_id": "g_planner_schema",
                "user_goal_id": "goal_expected",
                "agent_id": "agent",
                "agent_name": "app",
                "app_id": "app",
                "session_id": "sess",
                "capability": "report.say",
                "operation_type": "skill_call",
                "query_type": QueryType.SKILL,
                "status": "created",
                "params": {"message": "done"},
                "metadata": {},
                "dependencies": [],
                "dependents": [],
                "resources": [],
                "preconditions": [],
                "required_permissions": [],
                "safety_constraints": {},
                "produces_facts": [],
                "consumes_facts": [],
                "resource_lease_ids": [],
                "audit_ids": [],
            }
        },
        "edges": [],
        "status": "created",
    }


def test_planner_identity_validator_rejects_node_identifier_drift():
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="original goal",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={
            "report": TaskNode.create(
                node_id="report",
                task_graph_id="g",
                user_goal_id="goal",
                agent_id="agent_drift",
                agent_name="app",
                app_id="app",
                session_id="sess",
                capability="report.say",
                query_type=QueryType.SKILL,
                params={"message": "done"},
            )
        },
    )

    with pytest.raises(ValueError, match="SCHEDULER_GRAPH_SCHEMA_INVALID"):
        _validate_planner_identity(
            graph,
            goal="original goal",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            admission=AdmissionController(),
        )
