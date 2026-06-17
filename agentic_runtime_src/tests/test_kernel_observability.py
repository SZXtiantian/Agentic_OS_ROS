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
                messages=[{"role": "user", "content": "status please"}],
                metadata={"session_id": "sess_observe"},
            ),
            timeout_s=1.0,
        )
        assert result.success is True

        status = service.status()
    finally:
        service.stop()

    assert status["scheduler"]["active"] is True
    assert status["scheduler"]["threads"]
    assert all(status["scheduler"]["threads"].values())
    assert "llm" in status["queues"]
    assert status["managers"]["llm"] == "ready"
    assert status["managers"]["storage"] == "ready"
    assert status["access"]["policy"] == "DefaultAccessPolicy"
    assert status["audit"]["enabled"] is True
    assert status["recent_syscalls"][-1]["queue_name"] == "llm"
    assert status["recent_syscalls"][-1]["status"] == "succeeded"
    assert audit.recent(limit=1)[0]["session_id"] == "sess_observe"


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


def test_kernel_stop_clears_live_threads_from_status(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    service.start()
    assert service.status()["scheduler"]["active"] is True

    service.stop()
    status = service.status()

    assert status["scheduler"]["active"] is False
    assert status["scheduler"]["threads"] == {}
