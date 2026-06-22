import pytest

from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
from agentic_os.kernel.hooks import InMemoryKernelEventSink
from agentic_os.kernel.storage import LSFSAdapter, StorageManager
from agentic_os.kernel.system_call import KernelSyscall


def test_sto_create_file_in_sandbox(tmp_path):
    storage = StorageManager(tmp_path / "storage")

    result = storage.address_request(
        KernelSyscall.create("agent_a", "storage", "sto_create_file", {"file_path": "reports/x.md"})
    )

    assert result["success"] is True
    assert (tmp_path / "storage" / "reports" / "x.md").is_file()


def test_sto_write_and_retrieve(tmp_path):
    storage = StorageManager(tmp_path / "storage")
    storage.address_request(
        KernelSyscall.create("agent_a", "storage", "sto_write", {"path": "reports/x.md", "content": "kitchen ok"})
    )

    result = storage.address_request(
        KernelSyscall.create("agent_a", "storage", "sto_retrieve", {"query": "kitchen"})
    )

    assert result["success"] is True
    assert result["retrieval_mode"] == "lexical_fts"
    assert result["semantic"] is False
    assert result["matches"][0]["relative_path"] == "reports/x.md"


def test_sto_rejects_absolute_path(tmp_path):
    storage = StorageManager(tmp_path / "storage")

    with pytest.raises(ValueError, match="unsafe storage path"):
        storage.address_request(
            KernelSyscall.create("agent_a", "storage", "sto_write", {"path": "/tmp/escape.md", "content": "bad"})
        )


def test_sto_rejects_audit_path_even_if_relative_escape_attempt(tmp_path):
    storage = StorageManager(tmp_path / "storage")

    with pytest.raises(ValueError, match="unsafe storage path"):
        storage.address_request(
            KernelSyscall.create("agent_a", "storage", "sto_write", {"path": "audit/log.jsonl", "content": "bad"})
        )


def test_sto_overwrite_requires_intervention(tmp_path):
    sink = InMemoryKernelEventSink()
    storage = StorageManager(tmp_path / "storage", access_manager=AccessManager(), event_sink=sink)
    storage.write("reports/x.md", "old")

    result = storage.address_request(
        KernelSyscall.create("agent_a", "storage", "sto_write", {"path": "reports/x.md", "content": "new"})
    )

    assert result["success"] is False
    assert result["error_code"] == "ACCESS_INTERVENTION_REQUIRED"
    assert result["requires_intervention"] is True
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "storage.audit"][-1]
    assert audit["metadata"]["action"] == "overwrite"
    assert audit["metadata"]["success"] is False
    assert audit["metadata"]["error_code"] == "ACCESS_INTERVENTION_REQUIRED"


def test_sto_rollback_restores_previous_content(tmp_path):
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    storage = StorageManager(tmp_path / "storage", access_manager=access)
    storage.write("reports/x.md", "old")
    storage.write("reports/x.md", "new")

    rollback = storage.address_request(
        KernelSyscall.create("agent_a", "storage", "sto_rollback", {"path": "reports/x.md"})
    )

    assert rollback["success"] is True
    assert storage.read("reports/x.md")["content"] == "old"


def test_sto_share_updates_policy_only_after_confirmation(tmp_path):
    denied_storage = StorageManager(tmp_path / "denied", access_manager=AccessManager())
    denied_storage.write("reports/x.md", "content")

    denied = denied_storage.share("reports/x.md")

    assert denied["success"] is False
    assert denied["error_code"] == "ACCESS_INTERVENTION_REQUIRED"

    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    storage = StorageManager(tmp_path / "allowed", access_manager=access)
    storage.write("reports/x.md", "content")
    allowed = storage.share("reports/x.md", {"scope": "operator"})

    assert allowed["success"] is True
    assert allowed["sharing_policy"]["labels"] == ["shared"]
    assert allowed["sharing_policy"]["metadata"] == {"scope": "operator"}
    assert storage.share_policy("reports/x.md")["sharing_policy"]["metadata"] == {"scope": "operator"}


def test_dangerous_storage_operations_emit_audit_events(tmp_path):
    sink = InMemoryKernelEventSink()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    storage = StorageManager(tmp_path / "storage", access_manager=access, event_sink=sink)
    storage.write("reports/x.md", "old")
    storage.write("reports/x.md", "new")

    rollback = storage.rollback("reports/x.md")
    share = storage.share("reports/x.md", {"scope": "operator"})
    delete = storage.delete("reports/x.md")

    assert rollback["success"] is True
    assert share["success"] is True
    assert delete["success"] is True
    events = [event for event in sink.recent(limit=20) if event["event_type"] == "storage.audit"]
    assert [event["metadata"]["action"] for event in events] == ["overwrite", "rollback", "share", "delete"]
    assert all(event["metadata"]["success"] is True for event in events)
    assert all(event["metadata"]["irreversible"] is True for event in events)


def test_denied_dangerous_storage_operation_emits_audit_event(tmp_path):
    sink = InMemoryKernelEventSink()
    storage = StorageManager(tmp_path / "storage", access_manager=AccessManager(), event_sink=sink)
    storage.write("reports/x.md", "content")

    denied = storage.delete("reports/x.md")

    assert denied["success"] is False
    assert denied["error_code"] == "ACCESS_INTERVENTION_REQUIRED"
    audit = [event for event in sink.recent(limit=20) if event["event_type"] == "storage.audit"][-1]
    assert audit["metadata"]["action"] == "delete"
    assert audit["metadata"]["success"] is False
    assert audit["metadata"]["error_code"] == "ACCESS_INTERVENTION_REQUIRED"


def test_lsfs_adapter_status_implemented_true_when_enabled(tmp_path):
    adapter = LSFSAdapter(tmp_path / "lsfs")

    status = adapter.status()

    assert status["enabled"] is True
    assert status["implemented"] is True
    assert status["root"] == str(tmp_path / "lsfs")


def test_lsfs_adapter_mount_write_retrieve_and_version(tmp_path):
    adapter = LSFSAdapter(tmp_path / "lsfs")

    mounted = adapter.mount("workspace")
    first = adapter.write("workspace/reports/x.md", "old kitchen semantic note")
    second = adapter.write("workspace/reports/x.md", "new kitchen semantic note", metadata={"kind": "report"})
    retrieved = adapter.retrieve("kitchen", collection_name="workspace", limit=5)

    assert mounted["success"] is True
    assert (tmp_path / "lsfs" / "workspace").is_dir()
    assert first["version"] == ""
    assert second["version"].endswith(".bak")
    assert second["metadata"] == {"kind": "report"}
    assert retrieved["retrieval_mode"] == "lexical_fts"
    assert retrieved["semantic"] is False
    assert retrieved["matches"][0]["relative_path"] == "workspace/reports/x.md"
    assert "snippet" in retrieved["matches"][0]


def test_sto_rejects_bridge_profile_path(tmp_path):
    storage = StorageManager(tmp_path / "storage")

    with pytest.raises(ValueError, match="unsafe storage path"):
        storage.address_request(
            KernelSyscall.create(
                "agent_a",
                "storage",
                "sto_write",
                {"path": "bridge_profiles/robot.yaml", "content": "bad"},
            )
        )
