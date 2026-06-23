from agentic_runtime.memory import create_memory_manager
from agentic_runtime.memory.manager import MemoryManager


def test_sqlite_memory_provider_search_and_delete(tmp_path):
    manager = create_memory_manager("sqlite", tmp_path / "memory.sqlite3")
    manager.remember("app", "sess", "last_inspection", {"summary": "厨房 ok"})

    assert manager.recall("app", "last_inspection") == {"summary": "厨房 ok"}
    assert manager.search("app", "厨房")[0]["key"] == "last_inspection"
    assert manager.delete("app", "last_inspection") is False
    assert manager.recall("app", "last_inspection") == {"summary": "厨房 ok"}


def test_runtime_memory_provider_failure_is_not_converted_to_success():
    class RejectingProvider:
        def remember(self, app_id, session_id, key, value):
            return {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE", "reason": "database closed"}

        def recall(self, app_id, key):
            return None

        def search(self, app_id, query, limit=5):
            return []

        def delete(self, app_id, key):
            return False

    manager = MemoryManager(RejectingProvider())

    result = manager.remember("app", "sess", "last_inspection", {"summary": "厨房 ok"})

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_UNAVAILABLE"
    assert result["memory_id"] == "last_inspection"
