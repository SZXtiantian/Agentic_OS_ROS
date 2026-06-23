from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
from agentic_os.kernel.memory import (
    ChromaMemoryProvider,
    CompressedMemoryBlock,
    ContextInjector,
    ConversationExtractor,
    InMemoryMemoryProvider,
    HashEmbeddingProvider,
    HybridMemoryRetriever,
    MemoryManager,
    MemoryNote,
    RobotMemoryMetadata,
)
from agentic_os.kernel.storage import StorageManager
from agentic_os.kernel.system_call import LLMQuery


def test_memory_note_has_aios_metadata_fields():
    robot = RobotMemoryMetadata(robot_id="r1", place_id="kitchen", frame_id="map")
    note = MemoryNote(
        id="note_1",
        content="kitchen clean",
        owner_agent="agent_a",
        user_id="user_1",
        context="inspection",
        keywords=["kitchen"],
        tags=["inspection"],
        category="evidence",
        metadata={"robot": robot.to_dict()},
    )

    data = note.to_dict()

    assert data["context"] == "inspection"
    assert data["keywords"] == ["kitchen"]
    assert data["metadata"]["robot"]["place_id"] == "kitchen"


def test_memory_add_get_retrieve_lexical():
    manager = MemoryManager()
    manager.add(MemoryNote(id="n1", content="kitchen is clean", owner_agent="agent_a", tags=["room"]))

    fetched = manager.get("n1", "agent_a")
    retrieved = manager.retrieve("agent_a", "kitchen")

    assert fetched["success"] is True
    assert fetched["memory"]["content"] == "kitchen is clean"
    assert retrieved["memories"][0]["id"] == "n1"


def test_memory_private_access_denied_for_other_agent():
    manager = MemoryManager()
    manager.add(MemoryNote(id="n1", content="secret", owner_agent="agent_a"))

    result = manager.get("n1", "agent_b")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_FORBIDDEN"


def test_memory_shared_read_allowed_write_denied():
    manager = MemoryManager(access_manager=AccessManager())
    manager.add(MemoryNote(id="n1", content="shared", owner_agent="agent_a", sharing_policy="shared"))

    read = manager.get("n1", "agent_b")
    write = manager.update(
        MemoryNote(id="n1", content="changed", owner_agent="agent_a", sharing_policy="shared"),
        subject_agent="agent_b",
    )

    assert read["success"] is True
    assert write["success"] is False
    assert write["error_code"] == "ACCESS_SHARED_WRITE_DENIED"


def test_memory_eviction_moves_to_persistent_provider():
    ram = InMemoryMemoryProvider()
    persistent = InMemoryMemoryProvider()
    manager = MemoryManager(provider=ram, persistent_provider=persistent, max_notes_per_agent=1)

    manager.add(MemoryNote(id="n1", content="old kitchen note", owner_agent="agent_a"))
    manager.add(MemoryNote(id="n2", content="new kitchen note", owner_agent="agent_a"))

    assert ram.get_memory("n1", "agent_a")["success"] is False
    assert persistent.get_memory("n1", "agent_a")["success"] is True
    assert manager.get("n1", "agent_a")["success"] is True


def test_memory_get_does_not_fallback_after_primary_forbidden():
    ram = InMemoryMemoryProvider()
    persistent = InMemoryMemoryProvider()
    ram.add_memory(MemoryNote(id="n1", content="private primary", owner_agent="agent_a"))
    persistent.add_memory(MemoryNote(id="n1", content="shared persistent", owner_agent="agent_a", sharing_policy="shared"))
    manager = MemoryManager(provider=ram, persistent_provider=persistent)

    result = manager.get("n1", "agent_b")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_FORBIDDEN"


def test_memory_get_reports_persistent_provider_failure():
    class FailingPersistentProvider(InMemoryMemoryProvider):
        def get_memory(self, memory_id: str, agent_name: str = ""):
            return {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE", "reason": "persistent db closed"}

    manager = MemoryManager(provider=InMemoryMemoryProvider(), persistent_provider=FailingPersistentProvider())

    result = manager.get("missing", "agent_a")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_UNAVAILABLE"
    assert result["reason"] == "persistent db closed"


def test_memory_provider_success_field_must_be_boolean_on_remember():
    class MalformedProvider(InMemoryMemoryProvider):
        def add_memory(self, note):
            return {"success": "true", "memory_id": note.id}

    manager = MemoryManager(provider=MalformedProvider())

    result = manager.add(MemoryNote(id="n1", content="kitchen", owner_agent="agent_a"))

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_RESULT_INVALID"
    assert "success field must be boolean" in result["reason"]


def test_memory_provider_success_field_must_be_boolean_on_get():
    class MalformedProvider(InMemoryMemoryProvider):
        def get_memory(self, memory_id: str, agent_name: str = ""):
            return {"success": "false", "error_code": "MEMORY_NOT_FOUND"}

    manager = MemoryManager(provider=MalformedProvider())

    result = manager.get("n1", "agent_a")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_RESULT_INVALID"


def test_memory_provider_success_field_must_be_boolean_on_delete():
    class MalformedProvider(InMemoryMemoryProvider):
        def remove_memory(self, memory_id: str, agent_name: str = ""):
            return {"success": "false", "error_code": "MEMORY_NOT_FOUND"}

    manager = MemoryManager(
        provider=MalformedProvider(),
        access_manager=AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider()),
    )

    result = manager.remove("n1", "agent_a")

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_RESULT_INVALID"


def test_memory_retrieve_reports_persistent_provider_failure():
    class FailingPersistentProvider(InMemoryMemoryProvider):
        def retrieve_memory(self, query: str, agent_name: str, limit: int = 5, user_id: str = ""):
            return {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE", "reason": "persistent db closed"}

    ram = InMemoryMemoryProvider()
    manager = MemoryManager(provider=ram, persistent_provider=FailingPersistentProvider())

    result = manager.retrieve("agent_a", "kitchen", limit=5)

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_UNAVAILABLE"
    assert result["reason"] == "persistent db closed"


def test_memory_retrieve_rejects_non_boolean_provider_success():
    class MalformedProvider(InMemoryMemoryProvider):
        def retrieve_memory(self, query: str, agent_name: str, limit: int = 5, user_id: str = ""):
            return {"success": "true", "memories": []}

    manager = MemoryManager(provider=MalformedProvider())

    result = manager.retrieve("agent_a", "kitchen", limit=5)

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_RESULT_INVALID"


def test_two_tier_eviction_writes_compressed_block_to_storage(tmp_path):
    storage = StorageManager(tmp_path / "storage")
    robot_metadata = {
        "robot_id": "r1",
        "place_id": "kitchen",
        "frame_id": "map",
        "pose": {"x": 1.0},
        "sensor_refs": ["image://1"],
        "safety_context": {"localized": True},
        "retention_class": "task_log",
        "privacy": "private",
    }
    manager = MemoryManager(max_notes_per_agent=1, two_tier_enabled=True, storage_manager=storage)

    manager.add(
        MemoryNote(
            id="n1",
            content="old kitchen note with red block",
            owner_agent="agent_a",
            metadata={"robot": robot_metadata, "session_id": "sess_1"},
        )
    )
    manager.add(MemoryNote(id="n2", content="new kitchen note", owner_agent="agent_a"))

    blocks = manager.compressed_blocks["agent_a"]
    storage_result = storage.retrieve("red block", collection_name="memory_blocks", limit=5)
    retrieved = manager.retrieve("agent_a", "red block", limit=5)

    assert isinstance(blocks[0], CompressedMemoryBlock)
    assert blocks[0].storage_ref
    assert blocks[0].notes == ["n1"]
    assert blocks[0].metadata["note_metadata"][0]["robot"]["place_id"] == "kitchen"
    assert storage_result["matches"]
    assert retrieved["memories"][0]["metadata"]["compressed_block"]["notes"] == ["n1"]


def test_two_tier_eviction_rejects_non_boolean_storage_write_success():
    class MalformedStorage:
        def write(self, relative_path, content):
            return {"success": "true", "path": relative_path}

    manager = MemoryManager(max_notes_per_agent=1, two_tier_enabled=True, storage_manager=MalformedStorage())

    manager.add(MemoryNote(id="n1", content="old kitchen note", owner_agent="agent_a"))
    manager.add(MemoryNote(id="n2", content="new kitchen note", owner_agent="agent_a"))

    assert not manager.compressed_blocks["agent_a"][0].storage_ref


def test_memory_retrieve_reports_storage_block_backend_failure():
    class FailingStorage:
        def retrieve(self, query: str, collection_name: str = "", limit: int = 5):
            return {"success": False, "error_code": "STORAGE_INDEX_UNAVAILABLE", "reason": "fts db missing"}

    manager = MemoryManager(provider=InMemoryMemoryProvider(), two_tier_enabled=True, storage_manager=FailingStorage())

    result = manager.retrieve("agent_a", "red block", limit=5)

    assert result["success"] is False
    assert result["error_code"] == "STORAGE_INDEX_UNAVAILABLE"
    assert result["reason"] == "fts db missing"
    assert result["operation"] == "search_storage_blocks"


def test_memory_retrieve_rejects_non_boolean_storage_success():
    class MalformedStorage:
        def retrieve(self, query: str, collection_name: str = "", limit: int = 5):
            return {"success": "true", "matches": []}

    manager = MemoryManager(provider=InMemoryMemoryProvider(), two_tier_enabled=True, storage_manager=MalformedStorage())

    result = manager.retrieve("agent_a", "red block", limit=5)

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_STORAGE_RETRIEVE_FAILED"
    assert "success field must be boolean" in result["reason"]


def test_hash_embedding_provider_is_deterministic():
    provider = HashEmbeddingProvider(dimensions=8)

    assert provider.embed("red block") == provider.embed("red block")
    assert provider.embed("red block") != provider.embed("blue cube")


def test_hybrid_vector_search_ranking_and_place_filter():
    retriever = HybridMemoryRetriever(embedding_provider=HashEmbeddingProvider(dimensions=8))
    notes = [
        MemoryNote(
            id="n1",
            content="red block near sink",
            owner_agent="agent_a",
            metadata={"robot": {"place_id": "kitchen", "robot_id": "r1", "frame_id": "map"}},
        ),
        MemoryNote(
            id="n2",
            content="red block in hallway",
            owner_agent="agent_a",
            metadata={"robot": {"place_id": "hallway", "robot_id": "r1", "frame_id": "map"}},
        ),
        MemoryNote(id="n3", content="blue cube", owner_agent="agent_a"),
    ]

    ranked = retriever.retrieve(notes, "red block", limit=3)
    filtered = retriever.retrieve(notes, "red block", limit=3, filters={"place_id": "kitchen"})

    assert ranked[0].id in {"n1", "n2"}
    assert [note.id for note in filtered] == ["n1"]


def test_chroma_provider_dependency_missing_is_structured(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "chromadb", None)
    provider = ChromaMemoryProvider(enabled=True)

    result = provider.add_memory(MemoryNote(id="n1", content="hello", owner_agent="agent_a"))

    assert result["success"] is False
    assert result["error_code"] == "MEMORY_PROVIDER_DEPENDENCY_MISSING"


def test_context_injector_adds_retrieved_memory_to_llm_query():
    manager = MemoryManager()
    manager.add(MemoryNote(id="n1", content="kitchen has a blue block", owner_agent="agent_a"))
    injector = ContextInjector(manager)
    query = LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "What is in the kitchen?"}])

    injected = injector.inject("agent_a", query)

    assert injected.messages[0]["role"] == "system"
    assert "blue block" in injected.messages[0]["content"]


def test_conversation_extractor_creates_memory_note():
    manager = MemoryManager()
    extractor = ConversationExtractor(manager)

    note = extractor.extract_async("agent_a", "Where is the block?", "On the table.", user_id="user_1")

    assert note.id
    assert manager.retrieve("agent_a", "table")["memories"][0]["id"] == note.id
