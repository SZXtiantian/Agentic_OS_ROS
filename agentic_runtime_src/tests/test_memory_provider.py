from agentic_runtime.memory import create_memory_manager


def test_sqlite_memory_provider_search_and_delete(tmp_path):
    manager = create_memory_manager("sqlite", tmp_path / "memory.sqlite3")
    manager.remember("app", "sess", "last_inspection", {"summary": "厨房 ok"})

    assert manager.recall("app", "last_inspection") == {"summary": "厨房 ok"}
    assert manager.search("app", "厨房")[0]["key"] == "last_inspection"
    assert manager.delete("app", "last_inspection") is True
    assert manager.recall("app", "last_inspection") is None
