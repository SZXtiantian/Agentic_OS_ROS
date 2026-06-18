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
    """Deterministic cost/quality-aware routing."""

    def __init__(self, llm_configs: list[LLMConfig]) -> None:
        self.llm_configs = [config for config in llm_configs if config.enabled]

    def candidates(self, selected_llms: list[str] | None = None, capability: str = "chat") -> list[LLMConfig]:
        selected = set(selected_llms or [])
        candidates = [
            config
            for config in self.llm_configs
            if capability in config.capabilities and (not selected or config.name in selected)
        ]
        return sorted(
            candidates,
            key=lambda config: (
                -config.quality_score,
                config.cost_per_1k_input + config.cost_per_1k_output,
                config.name,
            ),
        )

    def select(self, selected_llms: list[str] | None = None, capability: str = "chat") -> LLMConfig | None:
        candidates = self.candidates(selected_llms=selected_llms, capability=capability)
        return candidates[0] if candidates else None
