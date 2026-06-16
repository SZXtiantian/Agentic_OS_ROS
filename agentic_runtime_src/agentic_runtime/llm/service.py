from __future__ import annotations

from typing import Any

from .client import OpenAICompatibleChatClient


class LLMChat:
    """AgenticOS-owned LLM chat facade.

    Agent Apps and system agents should depend on this facade instead of
    constructing provider clients directly. Provider selection, secrets, model
    config, timeouts, and output parsing stay in AgenticOS Runtime.
    """

    def __init__(self, client: OpenAICompatibleChatClient | None = None) -> None:
        self._client = client or OpenAICompatibleChatClient()

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self._client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
