from __future__ import annotations

from agentic_os.kernel.system_call import LLMQuery

from .memory_formatter import format_memory


class ContextInjector:
    def __init__(self, memory_manager, max_memories: int = 5) -> None:
        self.memory_manager = memory_manager
        self.max_memories = max_memories

    def inject(self, agent_name: str, llm_query: LLMQuery) -> LLMQuery:
        latest_user = ""
        for message in reversed(llm_query.messages):
            if message.get("role") == "user":
                latest_user = str(message.get("content", ""))
                break
        result = self.memory_manager.retrieve(agent_name, latest_user, limit=self.max_memories)
        memories = result.get("memories", []) if result.get("success") else []
        if not memories:
            return llm_query
        system_message = {"role": "system", "content": "Relevant memory:\n" + format_memory(memories)}
        llm_query.messages = [system_message, *llm_query.messages]
        return llm_query
