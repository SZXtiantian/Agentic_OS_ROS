from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .config import LLMConfig, load_llm_config
from .errors import LLMError


class OpenAICompatibleChatClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or load_llm_config()

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        config = self.config.require_ready()
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self._chat_url(config),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_s) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise LLMError("LLM_PROVIDER_REQUEST_FAILED", f"LLM provider returned HTTP {exc.code}: {detail[:240]}") from exc
        except urllib.error.URLError as exc:
            raise LLMError("LLM_PROVIDER_REQUEST_FAILED", str(exc.reason)) from exc
        except TimeoutError as exc:
            raise LLMError("LLM_TIMEOUT", "LLM request timed out") from exc
        except OSError as exc:
            raise LLMError("LLM_PROVIDER_REQUEST_FAILED", str(exc)) from exc

        content = self._extract_message_content(body)
        return self._parse_json_object(content)

    def _chat_url(self, config: LLMConfig) -> str:
        return f"{config.base_url}/chat/completions"

    def _extract_message_content(self, body: str) -> str:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM_RESPONSE_INVALID_JSON", "LLM response body is not JSON") from exc
        try:
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM_RESPONSE_INVALID_SHAPE", "LLM response does not contain choices[0].message.content") from exc
        if not isinstance(content, str):
            raise LLMError("LLM_RESPONSE_INVALID_SHAPE", "LLM message content is not a string")
        return content

    def _parse_json_object(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            raise LLMError("LLM_OUTPUT_MARKDOWN", "LLM output must be raw JSON, not a markdown fence")
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM_OUTPUT_INVALID_JSON", "LLM output is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMError("LLM_OUTPUT_NOT_OBJECT", "LLM output must be a JSON object")
        return parsed
