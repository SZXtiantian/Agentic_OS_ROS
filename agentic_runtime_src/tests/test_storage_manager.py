import pytest

from agentic_os.kernel.storage import StorageManager as KernelStorageManager

from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.storage import StorageManager


def test_storage_manager_writes_artifact_inside_session_root(tmp_path):
    manager = StorageManager(tmp_path / "storage")
    record = manager.write_artifact("sess_1", "inspection_report.json", {"ok": True}, "inspection_report")

    assert record.artifact_type == "inspection_report"
    assert record.path.endswith("sess_1/inspection_report.json")


def test_storage_manager_rejects_path_traversal(tmp_path):
    manager = StorageManager(tmp_path / "storage")
    with pytest.raises(AgenticRuntimeError) as exc:
        manager.write_artifact("sess_1", "../escape.json", {"bad": True})
    assert exc.value.code == "STORAGE_PATH_INVALID"


def test_kernel_storage_list_root_allowed(tmp_path):
    manager = KernelStorageManager(tmp_path / "storage")
    manager.write("reports/inspection.json", {"ok": True})

    listed = manager.list(".")

    assert listed["success"] is True
    assert listed["entries"] == ["reports"]


def test_kernel_storage_write_root_forbidden(tmp_path):
    manager = KernelStorageManager(tmp_path / "storage")

    with pytest.raises(ValueError, match="unsafe storage path"):
        manager.write(".", {"bad": True})


def test_kernel_storage_rejects_parent_traversal(tmp_path):
    manager = KernelStorageManager(tmp_path / "storage")

    with pytest.raises(ValueError, match="unsafe storage path"):
        manager.write("../escape.json", {"bad": True})


def test_kernel_storage_rejects_absolute_path(tmp_path):
    manager = KernelStorageManager(tmp_path / "storage")

    with pytest.raises(ValueError, match="unsafe storage path"):
        manager.write("/tmp/escape.json", {"bad": True})
