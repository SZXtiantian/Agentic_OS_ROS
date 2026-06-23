from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.context import ContextManager
from agentic_os.kernel.context.providers import SQLiteContextProvider
from agentic_os.kernel.hooks import InMemoryKernelEventSink
from agentic_os.kernel.system_call import ContextQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


def make_app() -> AppManifest:
    return AppManifest("context_test_app", "0", "", "main:run", [], [])


def test_context_sqlite_provider_persists_put_get(tmp_path):
    db_path = tmp_path / "context.sqlite3"
    provider = SQLiteContextProvider(db_path)
    put = provider.put(
        "agent_a",
        "sess_1",
        "context",
        "task.stage",
        {"stage": "inspect"},
        {"ttl_s": 60},
    )

    reopened = SQLiteContextProvider(db_path)
    got = reopened.get("agent_a", "sess_1", "context", "task.stage")

    assert put["success"] is True
    assert got is not None
    assert got["value"] == {"stage": "inspect"}
    assert reopened.status()["state"] == "ready"


def test_context_sqlite_status_exposes_real_provider_observability(tmp_path):
    db_path = tmp_path / "context.sqlite3"
    provider = SQLiteContextProvider(db_path)

    status = provider.status()

    assert status["state"] == "ready"
    assert status["provider"] == "sqlite"
    assert status["path"] == str(db_path)
    assert status["db_path"] == str(db_path)
    assert status["last_error"] == {"operation": "", "error_code": "", "reason": ""}


def test_context_provider_records_last_error_for_size_limit(tmp_path):
    provider = SQLiteContextProvider(tmp_path / "context.sqlite3", max_value_bytes=4)

    result = provider.put("agent_a", "sess_1", "context", "too.big", "12345", {})

    assert result["success"] is False
    assert result["error_code"] == "CONTEXT_SNAPSHOT_TOO_LARGE"
    assert provider.status()["last_error"]["operation"] == "put"
    assert provider.status()["last_error"]["error_code"] == "CONTEXT_SNAPSHOT_TOO_LARGE"


def test_context_manager_snapshot_recover_compat_persists(tmp_path):
    manager = ContextManager(tmp_path / "ctx")
    manager.snapshot("sess_1", "agent_a", task={"place": "kitchen"}, current_skill="robot.inspect_area")

    recovered = ContextManager(tmp_path / "ctx").recover("sess_1", "agent_a")

    assert recovered is not None
    assert recovered.task == {"place": "kitchen"}
    assert recovered.current_skill == "robot.inspect_area"


def test_context_syscall_queue_scheduler_roundtrip(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        put = service.execute_request(
            "agent_a",
            ContextQuery(
                operation_type="ctx_put",
                params={"key": "task.stage", "value": "inspect"},
                session_id="sess_1",
            ),
            timeout_s=1.0,
        )
        got = service.execute_request(
            "agent_a",
            ContextQuery(operation_type="ctx_get", params={"key": "task.stage"}, session_id="sess_1"),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert put.success is True
    assert got.success is True
    assert got.response.data["value"] == "inspect"
    assert put.metadata["queue_name"] == "context"
    assert service.status()["context"]["state"] == "ready"
    assert service.status()["queues"]["context"]["added_count"] >= 2


def test_context_snapshot_recover_and_compact(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        snap = service.execute_request(
            "agent_a",
            ContextQuery(
                operation_type="ctx_snapshot",
                params={"state": {"plan": ["inspect", "report"]}},
                session_id="sess_2",
                checkpoint="before_report",
            ),
            timeout_s=1.0,
        )
        recover = service.execute_request(
            "agent_a",
            ContextQuery(operation_type="ctx_recover", session_id="sess_2", checkpoint="before_report"),
            timeout_s=1.0,
        )
        compact = service.execute_request(
            "agent_a",
            ContextQuery(operation_type="ctx_compact", params={"max_tokens": 8}, session_id="sess_2"),
            timeout_s=1.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert snap.success is True
    assert recover.success is True
    assert recover.response.data["state"] == {"plan": ["inspect", "report"]}
    assert compact.success is True
    assert "compacted" in compact.response.data
    assert status["context"]["compact_policy"]["mode"] == "structural_truncation"
    assert status["context"]["compact_policy"]["semantic_summary"] is False
    compact_audits = [
        event
        for event in status["events"]["recent"]
        if event["event_type"] == "context.audit" and event["metadata"]["operation_type"] == "ctx_compact"
    ]
    assert compact_audits
    assert compact_audits[-1]["metadata"]["compact_mode"] == "structural_truncation"


def test_context_audit_does_not_leak_values(tmp_path):
    sink = InMemoryKernelEventSink()
    manager = ContextManager(tmp_path / "ctx", event_sink=sink)

    put = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="ctx_put",
            params={"session_id": "sess_1", "key": "secret.key", "value": "secret context value"},
        )
    )
    delete = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="ctx_delete",
            params={"session_id": "sess_1", "key": "secret.key"},
        )
    )

    assert put.success is True
    assert delete.success is True
    events = [event for event in sink.recent(limit=10) if event["event_type"] == "context.audit"]
    assert [event["metadata"]["operation_type"] for event in events] == ["ctx_put", "ctx_delete"]
    assert "secret context value" not in str(events)


def test_context_syscalls_emit_access_and_audit_events_without_value_leak(tmp_path):
    sink = InMemoryKernelEventSink()
    access = AccessManager(event_sink=sink)
    manager = ContextManager(tmp_path / "ctx", access_manager=access, event_sink=sink)

    put = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="ctx_put",
            params={"session_id": "sess_1", "key": "task.stage", "value": "private stage value"},
        )
    )
    got = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="ctx_get",
            params={"session_id": "sess_1", "key": "task.stage"},
        )
    )
    listed = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="ctx_list",
            params={"session_id": "sess_1", "prefix": "task."},
        )
    )
    deleted = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="ctx_delete",
            params={"session_id": "sess_1", "key": "task.stage"},
        )
    )

    assert all(response.success is True for response in (put, got, listed, deleted))
    checked = [event for event in sink.recent(limit=20) if event["event_type"] == "access.checked"]
    audits = [event for event in sink.recent(limit=20) if event["event_type"] == "context.audit"]
    assert [event["metadata"]["action"] for event in checked] == ["write", "read", "read", "context_delete"]
    assert all(event["metadata"]["resource_type"] == "context" for event in checked)
    assert [event["metadata"]["operation_type"] for event in audits] == [
        "ctx_put",
        "ctx_get",
        "ctx_list",
        "ctx_delete",
    ]
    assert "private stage value" not in str(audits)


def test_context_sdk_facade_uses_kernel_service(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    class Executor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("context SDK must use kernel service")

    async def run():
        service.start()
        try:
            ctx = AgentContext(Executor(), make_app(), "sess_sdk")
            put = await ctx.kernel.context.put("task.stage", "inspect", timeout_s=1.0)
            got = await ctx.kernel.context.get("task.stage", timeout_s=1.0)
            listed = await ctx.kernel.context.list(prefix="task.", timeout_s=1.0)
            assert put.success is True
            assert got.response.data["value"] == "inspect"
            assert listed.response.data["entries"][0]["key"] == "task.stage"
        finally:
            service.stop()

    asyncio.run(run())


def test_context_unavailable_status_and_error_code(tmp_path):
    blocking_file = tmp_path / "not_a_dir"
    blocking_file.write_text("x", encoding="utf-8")
    manager = ContextManager(provider=SQLiteContextProvider(blocking_file / "context.sqlite3"))

    response = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="ctx_get",
            params={"key": "x"},
            syscall_id="ksc_test",
            get_pid=lambda: 1,
        )
    )

    assert response.success is False
    assert response.error_code == "CONTEXT_PROVIDER_UNAVAILABLE"
    assert manager.status()["state"] == "unavailable"
    assert manager.status()["db_path"] == str(blocking_file / "context.sqlite3")
    assert manager.status()["last_error"]["error_code"] == "CONTEXT_PROVIDER_UNAVAILABLE"
