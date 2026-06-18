from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from agentic_os.kernel.system_call import KernelResponse, LLMQuery

from .errors import LLMCoreErrorCode
from .schema import LLMConfig
from .utils import normalize_hf_response, normalize_litellm_response, normalize_openai_response


class LLMProvider(Protocol):
    def complete(self, query: LLMQuery) -> KernelResponse:
        ...

    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        ...


class MockLLMProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, query: LLMQuery) -> KernelResponse:
        return KernelResponse(
            True,
            response_message={
                "model": self.config.name,
                "backend": self.config.backend,
                "messages": list(query.messages),
                "tools": query.tools,
                "response_format": query.response_format,
                "action_type": query.action_type,
            },
            metadata={"provider": self.config.name},
        )

    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        return [self.complete(query) for query in queries]


class UnsupportedLLMProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, query: LLMQuery) -> KernelResponse:
        return KernelResponse(
            False,
            error_code=LLMCoreErrorCode.PROVIDER_UNSUPPORTED,
            metadata={"backend": self.config.backend, "model": self.config.name},
        )


class OpenAICompatibleProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, query: LLMQuery) -> KernelResponse:
        api_key = self.config.api_key or (os.environ.get(self.config.api_key_env) if self.config.api_key_env else "")
        if not api_key:
            return KernelResponse(False, error_code=LLMCoreErrorCode.API_KEY_MISSING)
        if not self.config.hostname:
            return KernelResponse(False, error_code=LLMCoreErrorCode.REQUEST_FAILED, metadata={"reason": "hostname missing"})

        payload = {
            "model": self.config.name,
            "messages": query.messages,
            **query.params,
        }
        if query.tools is not None:
            payload["tools"] = query.tools
        if query.response_format is not None:
            payload["response_format"] = query.response_format
        request = urllib.request.Request(
            f"{self.config.hostname.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return KernelResponse(False, error_code=LLMCoreErrorCode.REQUEST_FAILED, metadata={"reason": str(exc)})
        except json.JSONDecodeError as exc:
            return KernelResponse(False, error_code=LLMCoreErrorCode.RESPONSE_INVALID, metadata={"reason": str(exc)})

        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            return KernelResponse(False, error_code=LLMCoreErrorCode.RESPONSE_INVALID, metadata={"reason": str(exc)})
        normalized = normalize_openai_response(body)
        return KernelResponse(True, response_message=normalized.to_dict(), metadata={"provider": self.config.name})


class VLLMOpenAIProvider(OpenAICompatibleProvider):
    pass


class LiteLLMProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, query: LLMQuery) -> KernelResponse:
        try:
            import litellm  # type: ignore[import-not-found]
        except ImportError:
            return KernelResponse.error(
                LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING,
                metadata={"backend": self.config.backend, "dependency": "litellm"},
            )
        try:
            body = litellm.completion(
                model=self.config.model or self.config.name,
                messages=query.messages,
                tools=query.tools,
                response_format=query.response_format,
                timeout=self.config.timeout_s,
            )
            normalized = normalize_litellm_response(body)
        except Exception as exc:
            return KernelResponse.error(LLMCoreErrorCode.REQUEST_FAILED, metadata={"reason": str(exc)})
        return KernelResponse.ok(normalized.to_dict(), metadata={"provider": self.config.name})


class HuggingFaceProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, query: LLMQuery) -> KernelResponse:
        try:
            import transformers  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return KernelResponse.error(
                LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING,
                metadata={"backend": self.config.backend, "dependency": "transformers"},
            )
        prompt = "\n".join(str(message.get("content", "")) for message in query.messages)
        normalized = normalize_hf_response(prompt)
        return KernelResponse.ok(normalized.to_dict(), metadata={"provider": self.config.name})
