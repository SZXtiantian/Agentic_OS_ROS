from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    name: str
    backend: str
    hostname: str = ""
    api_key_env: str = ""
    model: str | None = None
    enabled: bool = True
    api_key: str = ""
    capabilities: tuple[str, ...] = ("chat",)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    quality_score: float = 0.0
    cost_weight: float = 1.0
    quality_weight: float = 1.0
    timeout_s: float = 30.0
    max_batch_size: int = 1
    supports_tools: bool = False
    supports_json: bool = False
    supports_streaming: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMConfig":
        return cls(
            name=str(data["name"]),
            backend=str(data.get("backend") or "mock"),
            hostname=str(data.get("hostname") or data.get("base_url") or ""),
            api_key_env=str(data.get("api_key_env") or ""),
            model=str(data.get("model")) if data.get("model") is not None else None,
            enabled=bool(data.get("enabled", True)),
            api_key=str(data.get("api_key") or ""),
            capabilities=tuple(data.get("capabilities") or ("chat",)),
            cost_per_1k_input=float(data.get("cost_per_1k_input", 0.0)),
            cost_per_1k_output=float(data.get("cost_per_1k_output", 0.0)),
            quality_score=float(data.get("quality_score", data.get("quality_weight", 0.0))),
            cost_weight=float(data.get("cost_weight", 1.0)),
            quality_weight=float(data.get("quality_weight", 1.0)),
            timeout_s=float(data.get("timeout_s", 30.0)),
            max_batch_size=int(data.get("max_batch_size", 1)),
            supports_tools=bool(data.get("supports_tools", False)),
            supports_json=bool(data.get("supports_json", False)),
            supports_streaming=bool(data.get("supports_streaming", False)),
        )
