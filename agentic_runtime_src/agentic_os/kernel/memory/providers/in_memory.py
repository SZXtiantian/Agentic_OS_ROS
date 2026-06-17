from __future__ import annotations

from threading import RLock
from typing import Any

from ..note import MemoryNote, utc_now
from ..retrievers import LexicalMemoryRetriever


def can_read(note: MemoryNote, agent_name: str, user_id: str = "") -> bool:
    if note.owner_agent == agent_name:
        return True
    if note.sharing_policy not in {"shared", "app_shared", "operator_shared"}:
        return False
    return not user_id or not note.user_id or note.user_id == user_id


class InMemoryMemoryProvider:
    def __init__(self) -> None:
        self._notes: dict[str, MemoryNote] = {}
        self._lock = RLock()
        self._retriever = LexicalMemoryRetriever()

    def add_memory(self, note: MemoryNote) -> dict[str, Any]:
        with self._lock:
            self._notes[note.id] = note
        return {"success": True, "memory_id": note.id}

    def remove_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        with self._lock:
            note = self._notes.get(memory_id)
            if note is not None and agent_name and note.owner_agent != agent_name:
                return {"success": False, "memory_id": memory_id, "error_code": "MEMORY_FORBIDDEN"}
            existed = self._notes.pop(memory_id, None) is not None
        return {"success": existed, "memory_id": memory_id, "error_code": "" if existed else "MEMORY_NOT_FOUND"}

    def update_memory(self, note: MemoryNote) -> dict[str, Any]:
        with self._lock:
            original = self._notes.get(note.id)
            if original is None:
                return {"success": False, "memory_id": note.id, "error_code": "MEMORY_NOT_FOUND"}
            if original.owner_agent != note.owner_agent:
                return {"success": False, "memory_id": note.id, "error_code": "MEMORY_FORBIDDEN"}
            note.created_at = original.created_at
            note.updated_at = utc_now()
            self._notes[note.id] = note
        return {"success": True, "memory_id": note.id}

    def get_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        with self._lock:
            note = self._notes.get(memory_id)
        if note is None:
            return {"success": False, "error_code": "MEMORY_NOT_FOUND"}
        if agent_name and not can_read(note, agent_name):
            return {"success": False, "error_code": "MEMORY_FORBIDDEN"}
        return {"success": True, "memory": note.to_dict()}

    def retrieve_memory(self, query: str, agent_name: str, limit: int = 5, user_id: str = "") -> dict[str, Any]:
        with self._lock:
            readable = [note for note in self._notes.values() if can_read(note, agent_name, user_id)]
        matched = self._retriever.retrieve(readable, query, limit=limit)
        return {"success": True, "memories": [note.to_dict() for note in matched]}

    def list_notes(self, agent_name: str = "") -> list[MemoryNote]:
        with self._lock:
            notes = list(self._notes.values())
        if agent_name:
            notes = [note for note in notes if note.owner_agent == agent_name]
        return sorted(notes, key=lambda note: note.created_at)
