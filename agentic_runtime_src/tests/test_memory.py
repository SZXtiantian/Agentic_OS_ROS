from agentic_runtime.memory import SQLiteMemoryStore


def test_memory_remember_recall(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.remember("app", "sess", "last_inspection", {"ok": True})
    assert store.recall("app", "last_inspection") == {"ok": True}
