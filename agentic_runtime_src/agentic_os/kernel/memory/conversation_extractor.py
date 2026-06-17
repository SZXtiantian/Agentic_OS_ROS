from __future__ import annotations

from .note import MemoryNote


class ConversationExtractor:
    def __init__(self, memory_manager) -> None:
        self.memory_manager = memory_manager

    def extract_async(
        self,
        agent_name: str,
        user_message: str,
        assistant_message: str,
        user_id: str = "",
    ) -> MemoryNote:
        note = MemoryNote(
            content=f"User: {user_message}\nAssistant: {assistant_message}",
            owner_agent=agent_name,
            user_id=user_id,
            context="conversation",
            category="conversation",
            tags=["conversation"],
            metadata={"user_id": user_id, "owner_agent": agent_name},
        )
        self.memory_manager.add(note)
        return note
