from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agentic_runtime.config import find_repo_root

from .errors import LLMError


DEFAULT_PROVIDER = "yunwu"
DEFAULT_BASE_URL = "https://yunwu.ai/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_S = 20
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 800
DEFAULT_SECRET_FILE = Path("/opt/agentic/etc/secrets/yunwu.env")


@dataclass(frozen=True)
class LLMConfig:
    provider: str = DEFAULT_PROVIDER
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_s: int = DEFAULT_TIMEOUT_S
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    enabled: bool = True
    api_key: str = ""

    def require_ready(self) -> "LLMConfig":
        if not self.enabled:
            raise LLMError("LLM_DISABLED", "LLM provider is disabled in models.yaml")
        if not self.api_key:
            raise LLMError("LLM_API_KEY_MISSING", "LLM API key is not configured")
        if self.provider not in {"yunwu", "openai_compatible"}:
            raise LLMError("LLM_PROVIDER_UNSUPPORTED", f"unsupported LLM provider: {self.provider}")
        return self


def load_llm_config(config_path: str | Path | None = None, secret_path: str | Path | None = None) -> LLMConfig:
    data = _load_models_yaml(config_path)
    model_data = dict((data.get("models") or {}).get("default_reasoning_model") or {})

    provider = str(os.environ.get("AGENTIC_LLM_PROVIDER") or model_data.get("provider") or DEFAULT_PROVIDER)
    base_url = str(os.environ.get("AGENTIC_LLM_BASE_URL") or model_data.get("base_url") or DEFAULT_BASE_URL)
    model = str(os.environ.get("AGENTIC_LLM_MODEL") or model_data.get("model") or DEFAULT_MODEL)
    timeout_s = int(os.environ.get("AGENTIC_LLM_TIMEOUT_S") or model_data.get("timeout_s") or DEFAULT_TIMEOUT_S)
    temperature = float(os.environ.get("AGENTIC_LLM_TEMPERATURE") or model_data.get("temperature") or DEFAULT_TEMPERATURE)
    max_tokens = int(os.environ.get("AGENTIC_LLM_MAX_TOKENS") or model_data.get("max_tokens") or DEFAULT_MAX_TOKENS)
    enabled = _bool_from_value(model_data.get("enabled", True))
    api_key = os.environ.get("AGENTIC_LLM_API_KEY", "") or _load_secret_api_key(secret_path)

    return LLMConfig(
        provider=provider,
        base_url=_normalize_base_url(base_url),
        model=model,
        timeout_s=timeout_s,
        temperature=temperature,
        max_tokens=max_tokens,
        enabled=enabled,
        api_key=api_key,
    )


def _load_models_yaml(config_path: str | Path | None) -> dict[str, Any]:
    for path in _candidate_model_paths(config_path):
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def _candidate_model_paths(config_path: str | Path | None) -> list[Path]:
    paths: list[Path] = []
    if config_path:
        paths.append(Path(config_path).expanduser())
    if os.environ.get("AGENTIC_MODELS_CONFIG"):
        paths.append(Path(os.environ["AGENTIC_MODELS_CONFIG"]).expanduser())
    etc_root = Path(os.environ.get("AGENTIC_ETC", "/opt/agentic/etc")).expanduser()
    paths.append(etc_root / "models.yaml")
    paths.append(find_repo_root() / "configs" / "models.yaml")
    return paths


def _load_secret_api_key(secret_path: str | Path | None) -> str:
    path = Path(secret_path).expanduser() if secret_path else Path(os.environ.get("AGENTIC_LLM_SECRET_FILE", DEFAULT_SECRET_FILE))
    if not path.exists():
        return ""
    secrets: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        secrets[key.strip()] = value.strip().strip('"').strip("'")
    return secrets.get("AGENTIC_LLM_API_KEY") or secrets.get("YUNWU_API_KEY") or ""


def _normalize_base_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url


def _bool_from_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
