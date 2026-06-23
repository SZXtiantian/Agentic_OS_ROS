from agentic_runtime.memory import create_memory_manager
from agentic_runtime.memory.manager import MemoryManager
from agentic_runtime.memory.manager import RuntimeMemoryProviderAdapter


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


def test_runtime_memory_provider_non_structured_remember_is_not_success():
    class NonStructuredProvider:
        def remember(self, app_id, session_id, key, value):
            return None

        def recall(self, app_id, key):
            return None

        def search(self, app_id, query, limit=5):
            return []

        def delete(self, app_id, key):
            return False

    manager = MemoryManager(NonStructuredProvider())

    result = manager.remember("app", "sess", "last_inspection", {"summary": "厨房 ok"})

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_RESULT_INVALID"
    assert result["memory_id"] == "last_inspection"


def test_runtime_memory_provider_non_boolean_success_is_rejected():
    class StringSuccessProvider:
        def remember(self, app_id, session_id, key, value):
            return {"success": "false", "memory_id": key}

        def recall(self, app_id, key):
            return None

        def search(self, app_id, query, limit=5):
            return []

        def delete(self, app_id, key):
            return False

    manager = MemoryManager(StringSuccessProvider())

    result = manager.remember("app", "sess", "last_inspection", {"summary": "厨房 ok"})

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_RESULT_INVALID"
    assert "boolean success" in result["reason"]


def test_runtime_memory_recall_result_preserves_provider_exception():
    class RaisingRecallProvider:
        def remember(self, app_id, session_id, key, value):
            return {"success": True}

        def recall(self, app_id, key):
            raise OSError("database closed")

        def search(self, app_id, query, limit=5):
            return []

        def delete(self, app_id, key):
            return False

    manager = MemoryManager(RaisingRecallProvider())

    result = manager.recall_result("app", "last_inspection")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_UNAVAILABLE"


def test_runtime_memory_adapter_delete_preserves_structured_failure():
    class StructuredDeleteProvider:
        def remember(self, app_id, session_id, key, value):
            return {"success": True}

        def recall(self, app_id, key):
            return {"ok": True}

        def search(self, app_id, query, limit=5):
            return []

        def delete(self, app_id, key):
            return {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE", "reason": "db closed"}

    adapter = RuntimeMemoryProviderAdapter(StructuredDeleteProvider())

    result = adapter.remove_memory("last_inspection", "app")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_UNAVAILABLE"
    assert result["memory_id"] == "last_inspection"


def test_runtime_memory_adapter_delete_rejects_non_boolean_structured_result():
    class MalformedDeleteProvider:
        def remember(self, app_id, session_id, key, value):
            return {"success": True}

        def recall(self, app_id, key):
            return {"ok": True}

        def search(self, app_id, query, limit=5):
            return []

        def delete(self, app_id, key):
            return {"success": "false", "error_code": "MEMORY_PROVIDER_UNAVAILABLE"}

    adapter = RuntimeMemoryProviderAdapter(MalformedDeleteProvider())

    result = adapter.remove_memory("last_inspection", "app")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_RESULT_INVALID"


def test_runtime_memory_adapter_search_preserves_structured_failure():
    class StructuredSearchProvider:
        def remember(self, app_id, session_id, key, value):
            return {"success": True}

        def recall(self, app_id, key):
            return None

        def search(self, app_id, query, limit=5):
            return {"success": False, "error_code": "MEMORY_INDEX_UNAVAILABLE", "reason": "fts missing"}

        def delete(self, app_id, key):
            return False

    adapter = RuntimeMemoryProviderAdapter(StructuredSearchProvider())

    result = adapter.retrieve_memory("kitchen", "app")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_INDEX_UNAVAILABLE"


def test_runtime_memory_adapter_search_rejects_malformed_rows():
    class MalformedSearchProvider:
        def remember(self, app_id, session_id, key, value):
            return {"success": True}

        def recall(self, app_id, key):
            return None

        def search(self, app_id, query, limit=5):
            return ["not-a-row"]

        def delete(self, app_id, key):
            return False

    adapter = RuntimeMemoryProviderAdapter(MalformedSearchProvider())

    result = adapter.retrieve_memory("kitchen", "app")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_RESULT_INVALID"
