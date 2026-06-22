from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
from agentic_os.kernel.storage import StorageManager
from agentic_os.kernel.system_call import StorageQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


def make_app() -> AppManifest:
    return AppManifest("storage_test_app", "0", "", "main:run", [], [])


def test_storage_write_indexes_and_retrieves_with_sqlite_fts(tmp_path):
    storage = StorageManager(tmp_path / "storage")

    write = storage.write("reports/a.md", "kitchen inspection report", metadata={"kind": "report"})
    retrieved = storage.retrieve("kitchen", collection_name="reports", limit=5)
    status = storage.status()

    assert write["success"] is True
    assert retrieved["success"] is True
    assert retrieved["retrieval_mode"] == "lexical_fts"
    assert retrieved["semantic"] is False
    assert retrieved["matches"][0]["relative_path"] == "reports/a.md"
    assert retrieved["matches"][0]["metadata"]["kind"] == "report"
    assert status["index"]["state"] == "ready"
    assert status["index"]["indexed_count"] == 1
    assert status["semantic_retrieval"]["state"] == "unavailable"
    assert status["semantic_retrieval"]["error_code"] == "STORAGE_SEMANTIC_PROVIDER_UNCONFIGURED"


def test_storage_stat_history_and_specific_rollback(tmp_path):
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    storage = StorageManager(tmp_path / "storage", access_manager=access)
    storage.write("reports/a.md", "old")
    second = storage.write("reports/a.md", "new")

    stat = storage.stat("reports/a.md")
    history = storage.history("reports/a.md")
    rollback = storage.rollback("reports/a.md", version=second["version"])
    read = storage.read("reports/a.md")

    assert stat["success"] is True
    assert stat["sha256"]
    assert history["versions"][0]["version"] == second["version"]
    assert rollback["success"] is True
    assert read["content"] == "old"


def test_storage_share_registry_persists_across_manager_reopen(tmp_path):
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    root = tmp_path / "storage"
    storage = StorageManager(root, access_manager=access)
    storage.write("reports/a.md", "share me")

    shared = storage.share("reports/a.md", {"scope": "operator"})
    reopened = StorageManager(root)
    policy = reopened.share_policy("reports/a.md")
    status = reopened.status()

    assert shared["success"] is True
    assert shared["share_registry_path"] == str(root / ".storage_index.sqlite3")
    assert policy["success"] is True
    assert policy["sharing_policy"]["labels"] == ["shared"]
    assert policy["sharing_policy"]["metadata"] == {"scope": "operator"}
    assert status["share_registry"]["state"] == "ready"
    assert status["share_registry"]["share_count"] == 1


def test_storage_syscall_roundtrip_and_status(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        mounted = service.execute_request(
            "agent_a",
            StorageQuery(operation_type="sto_mount", params={"collection_name": "reports"}),
            timeout_s=1.0,
        )
        written = service.execute_request(
            "agent_a",
            StorageQuery(operation_type="sto_write", params={"path": "reports/a.md", "content": "blue cube report"}),
            timeout_s=1.0,
        )
        stat = service.execute_request(
            "agent_a",
            StorageQuery(operation_type="sto_stat", params={"path": "reports/a.md"}),
            timeout_s=1.0,
        )
        retrieved = service.execute_request(
            "agent_a",
            StorageQuery(operation_type="sto_retrieve", params={"query": "blue", "collection_name": "reports"}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert mounted.success is True
    assert written.success is True
    assert stat.response.data["size_bytes"] > 0
    assert retrieved.response.data["matches"][0]["relative_path"] == "reports/a.md"
    assert service.status()["storage"]["index"]["state"] == "ready"
    assert service.status()["queues"]["storage"]["added_count"] >= 4


def test_storage_delete_and_share_require_intervention_in_kernel_service(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        service.execute_request(
            "agent_a",
            StorageQuery(operation_type="sto_write", params={"path": "reports/a.md", "content": "content"}),
            timeout_s=1.0,
        )
        delete = service.execute_request(
            "agent_a",
            StorageQuery(operation_type="sto_delete", params={"path": "reports/a.md"}),
            timeout_s=1.0,
        )
        share = service.execute_request(
            "agent_a",
            StorageQuery(operation_type="sto_share", params={"path": "reports/a.md", "metadata": {"scope": "operator"}}),
            timeout_s=1.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert delete.success is False
    assert delete.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert share.success is False
    assert share.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert any(event["event_type"] == "access.checked" for event in status["events"]["recent"])


def test_storage_sdk_facade_uses_kernel_service(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    class Executor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("storage SDK must use kernel service")

    async def run():
        service.start()
        try:
            ctx = AgentContext(Executor(), make_app(), "sess_storage")
            await ctx.kernel.storage.mount("reports", timeout_s=1.0)
            written = await ctx.kernel.storage.write("reports/sdk.md", "sdk report", timeout_s=1.0)
            stat = await ctx.kernel.storage.stat("reports/sdk.md", timeout_s=1.0)
            retrieved = await ctx.kernel.storage.retrieve("sdk", collection_name="reports", limit=1)
            assert written.success is True
            assert stat.response.data["size_bytes"] == len("sdk report")
            assert retrieved.response.data["matches"][0]["relative_path"] == "reports/sdk.md"
        finally:
            service.stop()

    asyncio.run(run())


def test_storage_index_unavailable_is_stable(tmp_path):
    storage = StorageManager(tmp_path / "storage")
    storage._index_available = False
    storage._index_error = "forced failure"

    result = storage.retrieve("anything")

    assert result["success"] is False
    assert result["error_code"] == "STORAGE_INDEX_UNAVAILABLE"
    assert storage.status()["index"]["state"] == "unavailable"
