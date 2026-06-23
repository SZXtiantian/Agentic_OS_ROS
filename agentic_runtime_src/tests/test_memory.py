from agentic_runtime.memory import SQLiteMemoryStore


def test_memory_remember_recall(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    result = store.remember("app", "sess", "last_inspection", {"ok": True})
    assert result["success"] is True
    assert result["memory_id"] == "last_inspection"
    assert store.recall("app", "last_inspection") == {"ok": True}
    assert store.recall_result("app", "last_inspection")["value"] == {"ok": True}
