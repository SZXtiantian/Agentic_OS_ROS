from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any
from typing import Iterable

from agentic_os.kernel.system_call import KernelResponse

from .errors import LLMCoreErrorCode
from .schema import LLMConfig


def normalize_llm_configs(configs: Iterable[LLMConfig | dict]) -> list[LLMConfig]:
    normalized: list[LLMConfig] = []
    for config in configs:
        normalized.append(config if isinstance(config, LLMConfig) else LLMConfig.from_dict(config))
    return normalized


@dataclass
class NormalizedLLMMessage:
    role: str = "assistant"
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_openai_response(body: Any) -> NormalizedLLMMessage:
    if hasattr(body, "model_dump"):
        body = body.model_dump()
    if not isinstance(body, dict):
        raise ValueError("OpenAI-compatible response must be a dict")
    choice = (body.get("choices") or [{}])[0]
    message = dict(choice.get("message") or {})
    return NormalizedLLMMessage(
        role=str(message.get("role") or "assistant"),
        content=str(message.get("content") or ""),
        tool_calls=list(message.get("tool_calls") or []),
        raw=body,
    )


def normalize_litellm_response(body: Any) -> NormalizedLLMMessage:
    return normalize_openai_response(body)


def normalize_hf_response(text: str, maybe_tool_calls: list[dict[str, Any]] | None = None) -> NormalizedLLMMessage:
    return NormalizedLLMMessage(content=text, tool_calls=list(maybe_tool_calls or []), raw=text)


def enforce_json_response(query_response_format: dict[str, Any] | None, response: KernelResponse) -> KernelResponse:
    if not response.success:
        return response
    if not query_response_format or query_response_format.get("type") != "json_object":
        return response
    text = _message_text(response.response_message)
    if text == "":
        return response
    try:
        response.metadata["json"] = json.loads(text)
    except json.JSONDecodeError:
        return KernelResponse.error(
            LLMCoreErrorCode.RESPONSE_JSON_INVALID,
            response_message=response.response_message,
            metadata={**dict(response.metadata), "raw_text": text},
        )
    return response


def _message_text(message: Any) -> str:
    if isinstance(message, dict):
        if "content" in message:
            return str(message.get("content") or "")
        if "text" in message:
            return str(message.get("text") or "")
        return ""
    return str(message or "")
