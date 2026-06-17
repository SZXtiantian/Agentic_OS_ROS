from __future__ import annotations

from typing import Iterable

from .schema import LLMConfig


def normalize_llm_configs(configs: Iterable[LLMConfig | dict]) -> list[LLMConfig]:
    normalized: list[LLMConfig] = []
    for config in configs:
        normalized.append(config if isinstance(config, LLMConfig) else LLMConfig.from_dict(config))
    return normalized
