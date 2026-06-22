from __future__ import annotations

from types import SimpleNamespace

from agentic_os.kernel.system_call import LLMQuery, MemoryQuery
from agentic_runtime.audit import AuditLogger
from agentic_runtime.kernel_service import KernelService


def test_kernel_status_reports_scheduler_queues_managers_and_recent_syscalls(tmp_path):
    audit = AuditLogger(tmp_path / "audit.jsonl")
    service = KernelService(
        config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"),
        audit_logger=audit,
    )

    service.start()
    try:
        result = service.execute_request(
            "observer_app",
            LLMQuery(
                operation_type="chat",
                messages=[{"role": "user", "content": "status please with secret content"}],
                metadata={"session_id": "sess_observe"},
            ),
            timeout_s=1.0,
        )
        assert result.success is False
        assert result.error_code == "LLM_PROVIDER_UNCONFIGURED"

        status = service.status()
    finally:
        service.stop()

    assert status["scheduler"]["active"] is True
    assert status["scheduler"]["threads"]
    assert all(status["scheduler"]["threads"].values())
    assert "llm" in status["queues"]
    assert status["managers"]["llm"] == "ready"
    assert status["managers"]["storage"] == "ready"
    assert status["manager_status"]["tool"]["tool_count"] >= 3
    assert status["llm"]["state"] == "unavailable"
    assert status["access"]["policy"] == "DefaultAccessPolicy"
    assert status["audit"]["enabled"] is True
    assert status["events"]["count"] > 0
    assert "syscall.created" in {event["event_type"] for event in status["events"]["recent"]}
    assert "queue.added" in {event["event_type"] for event in status["events"]["recent"]}
    assert "manager.started" in {event["event_type"] for event in status["events"]["recent"]}
    assert "manager.done" in {event["event_type"] for event in status["events"]["recent"]}
    llm_audits = [event for event in status["events"]["recent"] if event["event_type"] == "llm.audit"]
    assert llm_audits
    assert llm_audits[-1]["metadata"]["error_code"] == "LLM_PROVIDER_UNCONFIGURED"
    assert status["recent_syscalls"][-1]["queue_name"] == "llm"
    assert status["recent_syscalls"][-1]["syscall_id"].startswith("ksc_")
    assert status["recent_syscalls"][-1]["audit_id"].startswith("audit_")
    assert status["recent_syscalls"][-1]["status"] == "failed"
    assert status["recent_syscalls"][-1]["error_code"] == "LLM_PROVIDER_UNCONFIGURED"
    assert audit.recent(limit=1)[0]["session_id"] == "sess_observe"
    rendered_status = str(status)
    rendered_audit = str(audit.recent(limit=1)[0])
    assert "status please with secret content" not in rendered_status
    assert "status please with secret content" not in rendered_audit


def test_kernel_status_updates_after_failed_syscall(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    service.start()
    try:
        result = service.execute_request(
            "observer_app",
            MemoryQuery(operation_type="unknown_memory_operation"),
            timeout_s=1.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "MEMORY_OPERATION_UNSUPPORTED"
    assert status["recent_syscalls"][-1]["success"] is False
    assert status["recent_syscalls"][-1]["error_code"] == "MEMORY_OPERATION_UNSUPPORTED"
    assert "syscall.failed" in {event["event_type"] for event in status["events"]["recent"]}


def test_access_checked_event_is_recorded_for_tool_access_denial(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    service.start()
    try:
        result = service.execute_request(
            "observer_app",
            MemoryQuery(operation_type="remember", params={"memory_id": "x", "content": "private note"}),
            timeout_s=1.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert result.success is True
    access_events = [event for event in status["events"]["recent"] if event["event_type"] == "access.checked"]
    assert access_events
    assert access_events[-1]["metadata"]["allowed"] is True
    assert "private note" not in str(status)


def test_kernel_stop_clears_live_threads_from_status(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    service.start()
    assert service.status()["scheduler"]["active"] is True

    service.stop()
    status = service.status()

    assert status["scheduler"]["active"] is False
    assert status["scheduler"]["threads"] == {}
