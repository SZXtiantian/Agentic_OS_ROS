from __future__ import annotations

from typing import Any, Protocol

from .note import MemoryNote


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
