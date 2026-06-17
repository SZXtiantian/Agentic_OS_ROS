from __future__ import annotations

from threading import Lock

from .schema import LLMConfig


class SequentialRouting:
    def __init__(self, llm_configs: list[LLMConfig]) -> None:
        self.llm_configs = [config for config in llm_configs if config.enabled]
        self._idx = 0
        self._lock = Lock()

    def candidates(self, selected_llms: list[str] | None = None, capability: str = "chat") -> list[LLMConfig]:
        selected = set(selected_llms or [])
        candidates = [
            config
            for config in self.llm_configs
            if capability in config.capabilities and (not selected or config.name in selected)
        ]
        if not candidates:
            return []
        with self._lock:
            start = self._idx % len(candidates)
            self._idx += 1
        return candidates[start:] + candidates[:start]

    def select(self, selected_llms: list[str] | None = None, capability: str = "chat") -> LLMConfig | None:
        candidates = self.candidates(selected_llms=selected_llms, capability=capability)
        return candidates[0] if candidates else None


class SmartRouting:
    """Cost/quality-aware routing shell.

    v1 delegates to sequential routing while preserving the extension point.
    """

    def __init__(self, llm_configs: list[LLMConfig]) -> None:
        self._sequential = SequentialRouting(llm_configs)

    def candidates(self, selected_llms: list[str] | None = None, capability: str = "chat") -> list[LLMConfig]:
        return self._sequential.candidates(selected_llms=selected_llms, capability=capability)

    def select(self, selected_llms: list[str] | None = None, capability: str = "chat") -> LLMConfig | None:
        return self._sequential.select(selected_llms=selected_llms, capability=capability)
