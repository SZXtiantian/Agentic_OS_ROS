from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
from agentic_os.kernel.hooks import InMemoryKernelEventSink
from agentic_os.kernel.memory import MemoryManager, MemoryNote, SQLiteMemoryProvider
from agentic_os.kernel.system_call import MemoryQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


def make_app() -> AppManifest:
    return AppManifest("memory_test_app", "0", "", "main:run", [], [])


def test_sqlite_memory_provider_persists_and_searches_with_fts(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    provider = SQLiteMemoryProvider(db_path)
    provider.add_memory(MemoryNote(id="m1", content="kitchen inspection complete", owner_agent="agent_a"))

    reopened = SQLiteMemoryProvider(db_path)
    fetched = reopened.get_memory("m1", "agent_a")
    searched = reopened.retrieve_memory("kitchen", "agent_a", limit=5)

    assert fetched["success"] is True
    assert fetched["memory"]["content"] == "kitchen inspection complete"
    assert searched["success"] is True
    assert searched["memories"][0]["id"] == "m1"
    assert reopened.status()["index"]["state"] == "ready"


def test_sqlite_memory_status_exposes_real_provider_observability(tmp_path):
    db_path = tmp_path / "memory.sqlite3"
    provider = SQLiteMemoryProvider(db_path)

    status = provider.status()

    assert status["state"] == "ready"
    assert status["provider"] == "sqlite"
    assert status["path"] == str(db_path)
    assert status["db_path"] == str(db_path)
    assert status["fts_available"] is True
    assert status["index"]["type"] == "sqlite_fts5"
    assert status["last_error"] == {"operation": "", "error_code": "", "reason": ""}


def test_memory_manager_default_is_sqlite_not_in_memory():
    manager = MemoryManager()

    assert manager.status()["provider"] == "sqlite"
    assert manager.status()["path"].endswith(".sqlite3")


def test_memory_syscall_roundtrip_uses_kernel_queue(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        remembered = service.execute_request(
            "agent_a",
            MemoryQuery(
                operation_type="mem_remember",
                params={"memory_id": "m1", "content": "red block on table"},
                metadata={"kernel_internal": True},
            ),
            timeout_s=1.0,
        )
        got = service.execute_request(
            "agent_a",
            MemoryQuery(operation_type="mem_get", params={"memory_id": "m1"}, metadata={"kernel_internal": True}),
            timeout_s=1.0,
        )
        searched = service.execute_request(
            "agent_a",
            MemoryQuery(operation_type="mem_search", params={"query": "red", "limit": 5}, metadata={"kernel_internal": True}),
            timeout_s=1.0,
        )
        listed = service.execute_request(
            "agent_a",
            MemoryQuery(operation_type="mem_list", params={"limit": 5}, metadata={"kernel_internal": True}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert remembered.success is True
    assert got.response.data["memory"]["content"] == "red block on table"
    assert searched.response.data["memories"][0]["id"] == "m1"
    assert listed.response.data["memories"][0]["id"] == "m1"
    assert remembered.metadata["queue_name"] == "memory"
    assert service.status()["memory"]["provider"] == "sqlite"
    assert service.status()["queues"]["memory"]["added_count"] >= 4


def test_memory_update_and_delete_permission_denied_is_stable(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        service.execute_request(
            "agent_a",
            MemoryQuery(
                operation_type="mem_remember",
                params={"memory_id": "m1", "content": "original"},
                metadata={"kernel_internal": True},
            ),
            timeout_s=1.0,
        )
        updated = service.execute_request(
            "agent_a",
            MemoryQuery(
                operation_type="mem_update",
                params={"memory_id": "m1", "content": "changed"},
                metadata={"kernel_internal": True},
            ),
            timeout_s=1.0,
        )
        deleted = service.execute_request(
            "agent_a",
            MemoryQuery(operation_type="mem_delete", params={"memory_id": "m1"}, metadata={"kernel_internal": True}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert updated.success is True
    assert deleted.success is False
    assert deleted.error_code == "ACCESS_INTERVENTION_REQUIRED"


def test_memory_low_risk_operations_emit_access_and_audit_events(tmp_path):
    sink = InMemoryKernelEventSink()
    access = AccessManager(event_sink=sink)
    manager = MemoryManager(
        db_path=tmp_path / "memory.sqlite3",
        access_manager=access,
        event_sink=sink,
    )

    remembered = manager.add(MemoryNote(id="m1", content="blue cube on bench", owner_agent="agent_a"))
    fetched = manager.get("m1", "agent_a")
    searched = manager.retrieve("agent_a", "blue", limit=5)
    listed = manager.list("agent_a", limit=5)
    updated = manager.update(MemoryNote(id="m1", content="blue cube moved", owner_agent="agent_a"))

    assert all(item["success"] is True for item in (remembered, fetched, searched, listed, updated))
    audits = [event for event in sink.recent(limit=30) if event["event_type"] == "memory.audit"]
    checked = [event for event in sink.recent(limit=30) if event["event_type"] == "access.checked"]
    assert [event["metadata"]["action"] for event in audits] == [
        "remember",
        "get",
        "search",
        "list",
        "update",
    ]
    assert [event["metadata"]["action"] for event in checked] == [
        "write",
        "read",
        "search",
        "list",
        "write",
    ]
    assert all(event["metadata"]["irreversible"] is False for event in audits)
    assert all(event["metadata"]["allowed"] is True for event in checked)


def test_memory_export_import_success_uses_real_file_with_access_manager(tmp_path):
    export_path = tmp_path / "export.jsonl"
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    source = MemoryManager(db_path=tmp_path / "source.sqlite3", access_manager=access)
    target = MemoryManager(db_path=tmp_path / "target.sqlite3", access_manager=access)
    source.add(MemoryNote(id="m1", content="report ready", owner_agent="agent_a"))

    exported = source.export("agent_a", str(export_path))
    imported = target.import_("agent_a", str(export_path))
    fetched = target.get("m1", "agent_a")

    assert exported == {"success": True, "path": str(export_path), "count": 1}
    assert imported == {"success": True, "path": str(export_path), "count": 1}
    assert fetched["memory"]["content"] == "report ready"


def test_dangerous_memory_operations_require_access_manager(tmp_path):
    export_path = tmp_path / "export.jsonl"
    sink = InMemoryKernelEventSink()
    manager = MemoryManager(
        db_path=tmp_path / "memory.sqlite3",
        access_manager=None,
        event_sink=sink,
    )
    manager.add(MemoryNote(id="m1", content="report ready", owner_agent="agent_a"))

    exported = manager.export("agent_a", str(export_path))
    imported = manager.import_("agent_a", str(export_path))
    deleted = manager.remove("m1", "agent_a")

    assert exported["error_code"] == "ACCESS_MANAGER_UNAVAILABLE"
    assert imported["error_code"] == "ACCESS_MANAGER_UNAVAILABLE"
    assert deleted["error_code"] == "ACCESS_MANAGER_UNAVAILABLE"
    audits = [event for event in sink.recent(limit=20) if event["event_type"] == "memory.audit"]
    dangerous = [event for event in audits if event["metadata"]["irreversible"] is True]
    assert [event["metadata"]["action"] for event in dangerous] == ["export", "import", "delete"]
    assert all(event["metadata"]["error_code"] == "ACCESS_MANAGER_UNAVAILABLE" for event in dangerous)
    assert manager.get("m1", "agent_a")["success"] is True


def test_memory_import_invalid_json_returns_stable_error_and_audit(tmp_path):
    import_path = tmp_path / "bad.jsonl"
    import_path.write_text("{not-json}\n", encoding="utf-8")
    sink = InMemoryKernelEventSink()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    manager = MemoryManager(
        db_path=tmp_path / "memory.sqlite3",
        access_manager=access,
        event_sink=sink,
    )

    imported = manager.import_("agent_a", str(import_path))

    assert imported["success"] is False
    assert imported["error_code"] == "MEMORY_IMPORT_INVALID_JSON"
    assert imported["line_number"] == 1
    assert manager.status()["last_error"]["error_code"] == "MEMORY_IMPORT_INVALID_JSON"
    audit = [event for event in sink.recent(limit=20) if event["event_type"] == "memory.audit"][-1]
    assert audit["metadata"]["action"] == "import"
    assert audit["metadata"]["success"] is False
    assert audit["metadata"]["error_code"] == "MEMORY_IMPORT_INVALID_JSON"


def test_memory_export_file_error_returns_stable_error_and_audit(tmp_path):
    sink = InMemoryKernelEventSink()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    manager = MemoryManager(
        db_path=tmp_path / "memory.sqlite3",
        access_manager=access,
        event_sink=sink,
    )
    manager.add(MemoryNote(id="m1", content="report ready", owner_agent="agent_a"))

    exported = manager.export("agent_a", str(tmp_path))

    assert exported["success"] is False
    assert exported["error_code"] == "MEMORY_EXPORT_FAILED"
    assert manager.status()["last_error"]["error_code"] == "MEMORY_EXPORT_FAILED"
    audit = [event for event in sink.recent(limit=20) if event["event_type"] == "memory.audit"][-1]
    assert audit["metadata"]["action"] == "export"
    assert audit["metadata"]["success"] is False
    assert audit["metadata"]["error_code"] == "MEMORY_EXPORT_FAILED"


def test_dangerous_memory_operations_emit_audit_events(tmp_path):
    export_path = tmp_path / "memory.jsonl"
    sink = InMemoryKernelEventSink()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    manager = MemoryManager(
        db_path=tmp_path / "memory.sqlite3",
        access_manager=access,
        event_sink=sink,
    )
    manager.add(MemoryNote(id="m1", content="report ready", owner_agent="agent_a"))

    exported = manager.export("agent_a", str(export_path))
    deleted = manager.remove("m1", "agent_a")
    imported = manager.import_("agent_a", str(export_path))

    assert exported["success"] is True
    assert deleted["success"] is True
    assert imported["success"] is True
    events = [event for event in sink.recent(limit=20) if event["event_type"] == "memory.audit"]
    dangerous_events = [event for event in events if event["metadata"]["irreversible"] is True]
    assert [event["metadata"]["action"] for event in dangerous_events] == ["export", "delete", "import"]
    assert all(event["metadata"]["success"] is True for event in dangerous_events)


def test_denied_memory_delete_emits_audit_event(tmp_path):
    sink = InMemoryKernelEventSink()
    manager = MemoryManager(
        db_path=tmp_path / "memory.sqlite3",
        access_manager=AccessManager(),
        event_sink=sink,
    )
    manager.add(MemoryNote(id="m1", content="report ready", owner_agent="agent_a"))

    denied = manager.remove("m1", "agent_a")

    assert denied["success"] is False
    assert denied["error_code"] == "ACCESS_INTERVENTION_REQUIRED"
    audit = [event for event in sink.recent(limit=20) if event["event_type"] == "memory.audit"][-1]
    assert audit["metadata"]["action"] == "delete"
    assert audit["metadata"]["success"] is False
    assert audit["metadata"]["error_code"] == "ACCESS_INTERVENTION_REQUIRED"


def test_memory_export_syscall_permission_denied_is_auditable(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            MemoryQuery(
                operation_type="mem_export",
                params={"path": str(tmp_path / "memory.jsonl")},
                metadata={"kernel_internal": True},
            ),
            timeout_s=1.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert any(event["event_type"] == "access.checked" for event in status["events"]["recent"])
    assert any(
        event["event_type"] == "memory.audit"
        and event["metadata"]["error_code"] == "ACCESS_INTERVENTION_REQUIRED"
        for event in status["events"]["recent"]
    )


def test_memory_sdk_facade_uses_kernel_service(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    class Executor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("memory SDK must use kernel service")

    async def run():
        service.start()
        try:
            agent = service.create_agent(app_id=make_app().name, session_id="sess_mem", agent_id="agent_mem_sdk")
            service.start_agent(agent.agent_id)
            ctx = AgentContext(Executor(), make_app(), "sess_mem", agent_id=agent.agent_id)
            remembered = await ctx.kernel.memory.remember("blue cube on bench", key="m1", timeout_s=1.0)
            got = await ctx.kernel.memory.get("m1", timeout_s=1.0)
            searched = await ctx.kernel.memory.search("blue", timeout_s=1.0)
            assert remembered.success is True
            assert got.response.data["memory"]["content"] == "blue cube on bench"
            assert searched.response.data["memories"][0]["id"] == "m1"
        finally:
            service.stop()

    asyncio.run(run())


def test_memory_provider_unavailable_status_and_error(tmp_path):
    blocking_file = tmp_path / "not_a_dir"
    blocking_file.write_text("x", encoding="utf-8")
    manager = MemoryManager(provider=SQLiteMemoryProvider(blocking_file / "memory.sqlite3"))
    response = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="mem_get",
            params={"memory_id": "m1"},
        )
    )

    assert response.success is False
    assert response.error_code == "MEMORY_PROVIDER_UNAVAILABLE"
    assert manager.status()["state"] == "unavailable"
    assert manager.status()["last_error"]["error_code"] == "MEMORY_PROVIDER_UNAVAILABLE"
