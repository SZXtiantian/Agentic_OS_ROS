import pytest

from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
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
    storage = StorageManager(tmp_path / "storage", access_manager=AccessManager())
    storage.write("reports/x.md", "old")

    result = storage.address_request(
        KernelSyscall.create("agent_a", "storage", "sto_write", {"path": "reports/x.md", "content": "new"})
    )

    assert result["success"] is False
    assert result["error_code"] == "ACCESS_INTERVENTION_REQUIRED"
    assert result["requires_intervention"] is True


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


def test_lsfs_adapter_disabled_shell():
    assert LSFSAdapter().status() == {"enabled": False, "implemented": False}
