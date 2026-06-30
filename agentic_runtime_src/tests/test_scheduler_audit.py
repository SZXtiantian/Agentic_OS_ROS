from __future__ import annotations

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, QueryType, SchedulerAudit, TaskGraph, TaskNode


REQUIRED_SCHEDULER_AUDIT_EVENTS = {
    "scheduler.goal.submitted",
    "scheduler.graph.admitted",
    "scheduler.graph.rejected",
    "scheduler.node.ready",
    "scheduler.node.blocked",
    "scheduler.node.dispatched",
    "scheduler.node.completed",
    "scheduler.node.failed",
    "scheduler.node.stale",
    "scheduler.priority.computed",
    "scheduler.resource.lease_requested",
    "scheduler.resource.lease_acquired",
    "scheduler.resource.lease_rejected",
    "scheduler.resource.lease_released",
    "scheduler.resource.lease_expired",
    "scheduler.resource.priority_inheritance",
    "scheduler.environment.fact_created",
    "scheduler.environment.fact_expired",
    "scheduler.environment.fact_reused",
    "scheduler.preemption.requested",
    "scheduler.preemption.accepted",
    "scheduler.preemption.rejected",
    "scheduler.safety.interrupt",
    "scheduler.fusion.proposed",
    "scheduler.fusion.accepted",
    "scheduler.fusion.rejected",
    "scheduler.fusion.reuse_edge.accepted",
    "scheduler.fusion.reuse_edge.rejected",
    "scheduler.fusion.node_inserted",
    "scheduler.fusion.node_reordered",
    "scheduler.fusion.coverage_preserved",
    "scheduler.fusion.coverage_risk",
    "scheduler.fusion.stale_reuse_rejected",
    "scheduler.llm.real_call_started",
    "scheduler.llm.real_call_completed",
    "scheduler.llm.real_call_failed",
    "scheduler.debug.snapshot_exported",
    "scheduler.debug.dot_exported",
}


def test_scheduler_audit_events_are_emitted_for_admission_and_ready():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, event_sink=sink)
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
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node},
    )

    scheduler.submit_graph(graph)
    event_types = [event["event_type"] for event in sink.recent(limit=20)]

    assert "scheduler.graph.admitted" in event_types
    assert "scheduler.node.ready" in event_types


def test_scheduler_audit_events_include_required_envelope_and_redact_sensitive_values():
    sink = InMemoryKernelEventSink()
    audit = SchedulerAudit(event_sink=sink)

    audit.emit("scheduler.node.blocked", node_id="n", prompt="private prompt", error_code="SCHEDULER_PRECONDITION_NOT_MET", success=False)
    event = sink.recent(limit=1)[0]
    metadata = event["metadata"]

    assert event["timestamp"]
    for key in (
        "agent_id",
        "app_id",
        "session_id",
        "task_graph_id",
        "node_id",
        "syscall_id",
        "resource_lease_id",
        "goal_id",
        "success",
        "error_code",
        "sanitized_metadata",
    ):
        assert key in metadata
    assert metadata["node_id"] == "n"
    assert metadata["success"] is False
    assert metadata["error_code"] == "SCHEDULER_PRECONDITION_NOT_MET"
    assert metadata["prompt"] == "[REDACTED]"
    assert metadata["sanitized_metadata"] == {"prompt": "[REDACTED]"}


def test_required_scheduler_audit_event_types_have_emit_sites(runtime_src):
    scheduler_root = runtime_src / "agentic_os" / "kernel" / "scheduler"
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in scheduler_root.glob("*.py"))

    missing = sorted(event_type for event_type in REQUIRED_SCHEDULER_AUDIT_EVENTS if event_type not in source_text)

    assert missing == []
