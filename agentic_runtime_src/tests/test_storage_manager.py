import pytest

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
