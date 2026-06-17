from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    name: str
    backend: str
    enabled: bool = True
    hostname: str = ""
    api_key_env: str = ""
    api_key: str = ""
    capabilities: tuple[str, ...] = ("chat",)
    cost_weight: float = 1.0
    quality_weight: float = 1.0
    timeout_s: float = 60.0

    @classmethod
    def from_dict(cls, data: dict) -> "LLMConfig":
        return cls(
            name=str(data["name"]),
            backend=str(data.get("backend") or "mock"),
            enabled=bool(data.get("enabled", True)),
            hostname=str(data.get("hostname") or data.get("base_url") or ""),
            api_key_env=str(data.get("api_key_env") or ""),
            api_key=str(data.get("api_key") or ""),
            capabilities=tuple(data.get("capabilities") or ("chat",)),
            cost_weight=float(data.get("cost_weight", 1.0)),
            quality_weight=float(data.get("quality_weight", 1.0)),
            timeout_s=float(data.get("timeout_s", 60.0)),
        )
