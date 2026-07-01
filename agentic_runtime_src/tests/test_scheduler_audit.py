from __future__ import annotations

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.scheduler import (
    REQUIRED_SCHEDULER_AUDIT_EVENTS,
    EnvironmentAwareDAGScheduler,
    QueryType,
    SchedulerAudit,
    TaskGraph,
    TaskNode,
)
from agentic_runtime.audit import AuditLogger


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
    assert event["event_type"] == "scheduler.node.blocked"
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


def test_scheduler_audit_logger_record_args_include_event_type(tmp_path):
    audit_logger = AuditLogger(tmp_path / "scheduler_audit.jsonl")
    audit = SchedulerAudit(audit_logger=audit_logger)

    audit_id = audit.emit(
        "scheduler.node.failed",
        task_graph_id="g",
        node_id="n",
        error_code="SCHEDULER_DISPATCH_FAILED",
        success=False,
    )
    record = audit_logger.recent(limit=1)[0]

    assert audit_id == record["audit_id"]
    assert record["skill_name"] == "scheduler.node.failed"
    assert record["args"]["event_type"] == "scheduler.node.failed"
    assert record["args"]["task_graph_id"] == "g"
    assert record["args"]["node_id"] == "n"
    assert record["args"]["error_code"] == "SCHEDULER_DISPATCH_FAILED"
    assert "event_type" not in record["args"]["sanitized_metadata"]


def test_required_scheduler_audit_event_types_have_emit_sites(runtime_src):
    scheduler_root = runtime_src / "agentic_os" / "kernel" / "scheduler"
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in scheduler_root.glob("*.py"))

    missing = sorted(event_type for event_type in REQUIRED_SCHEDULER_AUDIT_EVENTS if event_type not in source_text)

    assert missing == []


def test_required_scheduler_audit_event_registry_matches_design_spec(repo_root):
    spec_text = (repo_root.parent / "AGENTIC_OS_ROS_ENV_AWARE_PRIORITY_DAG_SCHEDULER.md").read_text(encoding="utf-8")

    missing = sorted(event_type for event_type in REQUIRED_SCHEDULER_AUDIT_EVENTS if event_type not in spec_text)

    assert missing == []
