from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.memory import (
    ContextInjector,
    ConversationExtractor,
    InMemoryMemoryProvider,
    MemoryManager,
    MemoryNote,
    RobotMemoryMetadata,
)
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
