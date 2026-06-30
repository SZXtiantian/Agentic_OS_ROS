from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, FusionPlan, QueryType, ResourceRequest, TaskGraph, TaskNode
from agentic_os.kernel.scheduler.models import TaskNodeStatus
from agentic_os.kernel.scheduler.preconditions import Precondition


def _validate_debug_snapshot(snapshot):
    schema_path = Path(__file__).resolve().parents[1] / "agentic_os/kernel/scheduler/schemas/debug_snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(snapshot)


def test_debug_snapshot_and_dot_export_are_schema_valid_and_sanitized():
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, event_sink=InMemoryKernelEventSink())
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        params={"message": "private report text"},
        metadata={"api_key": "secret-value"},
        produces_facts=["cup_pose"],
        fusion_group_id="fusion_cup",
    )
    consumer = TaskNode.create(
        node_id="consumer",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.pick_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["cup_pose"],
        preconditions=[Precondition("cup_pose", min_confidence=0.9)],
        status=TaskNodeStatus.BLOCKED,
        error_code="SCHEDULER_PRECONDITION_NOT_MET",
        fusion_group_id="fusion_cup",
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="private user goal",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node, "consumer": consumer},
    )
    scheduler.submit_graph(graph)

    snapshot = scheduler.debug_snapshot()
    dot = scheduler.export_dot()

    _validate_debug_snapshot(snapshot)
    assert snapshot["success"] is True
    assert snapshot["error_code"] == ""
    assert snapshot["scheduler_policy"] == "env_aware_priority_dag"
    assert "secret-value" not in str(snapshot)
    assert "private user goal" not in str(snapshot)
    assert "private report text" not in str(snapshot)
    assert "digraph AgenticScheduler" in dot
    assert "report.say" in dot
    assert "produces=cup_pose" in dot
    assert "consumes=cup_pose" in dot
    assert "fusion=fusion_cup" in dot
    assert "error=SCHEDULER_FACT_NOT_FOUND" in dot


def test_dot_export_redacts_sensitive_untrusted_graph_text():
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, event_sink=InMemoryKernelEventSink())
    sensitive_node_id = "api_key=secret-value"
    node = TaskNode.create(
        node_id=sensitive_node_id,
        task_graph_id="private prompt graph",
        user_goal_id="goal",
        agent_id="agent_token_secret",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        produces_facts=["private_memory_fact"],
    )
    graph = TaskGraph.create(
        task_graph_id="private prompt graph",
        user_goal_id="goal",
        root_goal="report",
        agent_id="agent_token_secret",
        app_id="app",
        session_id="sess",
        nodes={sensitive_node_id: node},
    )
    scheduler.submit_graph(graph)

    dot = scheduler.export_dot()

    assert "digraph AgenticScheduler" in dot
    assert "[REDACTED:" in dot
    assert "report.say" in dot
    assert "secret-value" not in dot
    assert "private prompt graph" not in dot
    assert "agent_token_secret" not in dot
    assert "private_memory_fact" not in dot


def test_debug_snapshot_summarizes_fusion_audit_metadata():
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, event_sink=InMemoryKernelEventSink())
    scheduler.fusion_engine._plans.append(
        FusionPlan(
            fusion_plan_id="fusion_sensitive",
            incoming_graph_id="g",
            base_global_dag_revision=0,
            accepted=False,
            reason="not_applied",
            audit_metadata={
                "reasoning": "private LLM reasoning about the user's home",
                "prompt": "secret planner prompt",
                "operator_notes": "private operator note",
            },
        )
    )

    snapshot = scheduler.debug_snapshot()
    snapshot_text = str(snapshot)
    plan = snapshot["fusion_plans"][0]

    _validate_debug_snapshot(snapshot)
    assert "private LLM reasoning" not in snapshot_text
    assert "secret planner prompt" not in snapshot_text
    assert "private operator note" not in snapshot_text
    assert plan["audit_metadata"] == "[REDACTED]"
    assert set(plan["audit_summary"]) == {"sha256", "length", "keys"}


def test_debug_snapshot_summarizes_sensitive_resource_lease_handles_and_metadata():
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, event_sink=InMemoryKernelEventSink())
    node = TaskNode.create(
        node_id="lease_holder",
        task_graph_id="g_lease_debug",
        user_goal_id="goal_lease_debug",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        resources=[ResourceRequest(resource_id="camera", mode="exclusive")],
    )
    result = scheduler.resource_arbiter.try_acquire(node, at_ns=1)
    lease = result.leases[0]
    lease.agent_resource_handle_id = "handle-secret-token"
    lease.metadata["device_session"] = "session-secret-value"
    lease.metadata["api_key"] = "api-secret-value"

    snapshot = scheduler.debug_snapshot()
    snapshot_text = str(snapshot)
    snapshot_lease = snapshot["leases"][0]

    _validate_debug_snapshot(snapshot)
    assert snapshot_lease["lease_id"] == lease.lease_id
    assert snapshot_lease["resource_id"] == "camera"
    assert snapshot_lease["status"] == "acquired"
    assert "agent_resource_handle_id" not in snapshot_lease
    assert "metadata" not in snapshot_lease
    assert set(snapshot_lease["agent_resource_handle_summary"]) == {"sha256", "length"}
    assert set(snapshot_lease["lease_info_summary"]) == {"sha256", "length"}
    assert "handle-secret-token" not in snapshot_text
    assert "session-secret-value" not in snapshot_text
    assert "api-secret-value" not in snapshot_text


def test_debug_snapshot_failure_returns_stable_sanitized_error():
    event_sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, event_sink=event_sink)

    def raise_sensitive_error():
        raise RuntimeError("api_key=secret-value prompt=private user goal")

    scheduler.resource_arbiter.snapshot = raise_sensitive_error

    snapshot = scheduler.debug_snapshot()
    snapshot_text = str(snapshot)

    _validate_debug_snapshot(snapshot)
    assert snapshot["success"] is False
    assert snapshot["error_code"] == "SCHEDULER_DEBUG_EXPORT_FAILED"
    assert snapshot["message"] == "debug snapshot export failed"
    assert "secret-value" not in snapshot_text
    assert "private user goal" not in snapshot_text
    assert snapshot["provider_status_summary"]["failure"]["type"] == "RuntimeError"

    events = [event for event in event_sink.recent() if event["event_type"] == "scheduler.debug.snapshot_exported"]
    assert events[-1]["metadata"]["success"] is False
    assert events[-1]["metadata"]["error_code"] == "SCHEDULER_DEBUG_EXPORT_FAILED"


class SensitiveStatusKernelService:
    def kernel_status(self):
        raise RuntimeError("api_key=secret-value prompt=private operator request")


def test_debug_snapshot_sanitizes_provider_status_exception_text():
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        kernel_service=SensitiveStatusKernelService(),
        event_sink=InMemoryKernelEventSink(),
    )

    snapshot = scheduler.debug_snapshot()
    snapshot_text = str(snapshot)
    failure = snapshot["provider_status_summary"]["failure"]

    _validate_debug_snapshot(snapshot)
    assert snapshot["success"] is True
    assert snapshot["provider_status_summary"]["error_code"] == "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE"
    assert failure["type"] == "RuntimeError"
    assert set(failure) == {"type", "message_sha256", "message_length"}
    assert "secret-value" not in snapshot_text
    assert "private operator request" not in snapshot_text


def test_dot_export_failure_returns_stable_graph_and_audit_event():
    event_sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {}, event_sink=event_sink)

    dot = scheduler.export_dot(task_graph_id="missing_graph")

    assert "digraph AgenticScheduler" in dot
    assert "SCHEDULER_DEBUG_EXPORT_FAILED" in dot
    assert "missing_graph" not in dot

    events = [event for event in event_sink.recent() if event["event_type"] == "scheduler.debug.dot_exported"]
    assert events[-1]["metadata"]["success"] is False
    assert events[-1]["metadata"]["error_code"] == "SCHEDULER_DEBUG_EXPORT_FAILED"
    assert events[-1]["metadata"]["task_graph_id"] == "missing_graph"
