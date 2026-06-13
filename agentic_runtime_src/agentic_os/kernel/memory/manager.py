from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from agentic_os.kernel.system_call import KernelSyscall


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryNote:
    content: Any
    id: str = field(default_factory=lambda: f"mem_{uuid4().hex}")
    owner_agent: str = ""
    user_id: str = ""
    sharing_policy: str = "private"
    memory_type: str = "episodic"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "owner_agent": self.owner_agent,
            "user_id": self.user_id,
            "sharing_policy": self.sharing_policy,
            "memory_type": self.memory_type,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MemoryProvider(Protocol):
    def add_memory(self, note: MemoryNote) -> dict[str, Any]:
        ...

    def remove_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        ...

    def update_memory(self, note: MemoryNote) -> dict[str, Any]:
        ...

    def get_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        ...

    def retrieve_memory(self, query: str, agent_name: str, limit: int = 5, user_id: str = "") -> dict[str, Any]:
        ...


def _can_read(note: MemoryNote, agent_name: str, user_id: str = "") -> bool:
    is_owner = note.owner_agent == agent_name
    if is_owner:
        return True
    if note.sharing_policy != "shared":
        return False
    return not user_id or note.user_id == user_id


class InMemoryMemoryProvider:
    """Small provider that ports AIOS memory-provider semantics without vector DB dependencies."""

    def __init__(self) -> None:
        self._notes: dict[str, MemoryNote] = {}
        self._lock = RLock()

    def add_memory(self, note: MemoryNote) -> dict[str, Any]:
        with self._lock:
            self._notes[note.id] = note
        return {"success": True, "memory_id": note.id}

    def remove_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        with self._lock:
            note = self._notes.get(memory_id)
            if note is not None and agent_name and not _can_read(note, agent_name):
                return {"success": False, "memory_id": memory_id, "error_code": "MEMORY_FORBIDDEN"}
            existed = self._notes.pop(memory_id, None) is not None
        return {"success": existed, "memory_id": memory_id, "error_code": "" if existed else "MEMORY_NOT_FOUND"}

    def update_memory(self, note: MemoryNote) -> dict[str, Any]:
        with self._lock:
            if note.id not in self._notes:
                return {"success": False, "memory_id": note.id, "error_code": "MEMORY_NOT_FOUND"}
            original = self._notes[note.id]
            note.created_at = original.created_at
            note.updated_at = utc_now()
            self._notes[note.id] = note
        return {"success": True, "memory_id": note.id}

    def get_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        with self._lock:
            note = self._notes.get(memory_id)
        if note is None:
            return {"success": False, "error_code": "MEMORY_NOT_FOUND"}
        if agent_name and not _can_read(note, agent_name):
            return {"success": False, "error_code": "MEMORY_FORBIDDEN"}
        return {"success": True, "memory": note.to_dict()}

    def retrieve_memory(self, query: str, agent_name: str, limit: int = 5, user_id: str = "") -> dict[str, Any]:
        query_text = str(query).lower()
        with self._lock:
            candidates = list(self._notes.values())
        readable = [note for note in candidates if _can_read(note, agent_name, user_id)]
        matched = [
            note
            for note in readable
            if query_text in str(note.content).lower()
            or any(query_text in tag.lower() for tag in note.tags)
        ]
        return {"success": True, "memories": [note.to_dict() for note in matched[:limit]]}


class MemoryManager:
    """Syscall-facing memory manager.

    AIOS routes MemorySyscall objects through a manager/provider split. This
    class keeps that shape and accepts AgenticOS ``KernelSyscall`` objects.
    """

    def __init__(self, provider: MemoryProvider | None = None) -> None:
        self.provider = provider or InMemoryMemoryProvider()

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        operation = syscall.operation_type
        params = syscall.params
        if operation in {"add_memory", "remember"}:
            note = self._note_from_params(syscall.agent_name, params)
            return self.provider.add_memory(note)
        if operation in {"remove_memory", "delete"}:
            return self.provider.remove_memory(str(params["memory_id"]), syscall.agent_name)
        if operation == "update_memory":
            note = self._note_from_params(syscall.agent_name, params)
            return self.provider.update_memory(note)
        if operation in {"get_memory", "recall"}:
            return self.provider.get_memory(str(params["memory_id"]), syscall.agent_name)
        if operation in {"retrieve_memory", "search"}:
            return self.provider.retrieve_memory(
                str(params.get("query") or params.get("content") or ""),
                syscall.agent_name,
                int(params.get("limit", params.get("k", 5))),
                str(params.get("user_id", "")),
            )
        return {"success": False, "error_code": "MEMORY_OPERATION_UNSUPPORTED", "operation": operation}

    def _note_from_params(self, agent_name: str, params: dict[str, Any]) -> MemoryNote:
        metadata = dict(params.get("metadata") or {})
        return MemoryNote(
            id=str(params.get("memory_id") or params.get("id") or f"mem_{uuid4().hex}"),
            content=params.get("content", params.get("value", "")),
            owner_agent=str(metadata.get("owner_agent") or params.get("owner_agent") or agent_name),
            user_id=str(metadata.get("user_id") or params.get("user_id") or ""),
            sharing_policy=str(metadata.get("sharing_policy") or params.get("sharing_policy") or "private"),
            memory_type=str(metadata.get("memory_type") or params.get("memory_type") or "episodic"),
            tags=list(metadata.get("tags") or params.get("tags") or []),
            metadata=metadata,
        )
