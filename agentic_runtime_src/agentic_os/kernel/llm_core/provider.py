from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from agentic_os.kernel.system_call import KernelResponse, LLMQuery

from .errors import LLMCoreErrorCode
from .schema import LLMConfig
from .utils import normalize_litellm_response, normalize_openai_response


class LLMProvider(Protocol):
    def complete(self, query: LLMQuery) -> KernelResponse:
        ...

    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        ...


class UnsupportedLLMProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, query: LLMQuery) -> KernelResponse:
        return KernelResponse(
            False,
            error_code=LLMCoreErrorCode.PROVIDER_UNAVAILABLE,
            metadata={"backend": self.config.backend, "model": self.config.name},
        )


class OpenAICompatibleProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, query: LLMQuery) -> KernelResponse:
        if query.action_type == "embed" or query.operation_type in {"llm_embed", "embed"}:
            return self.embed(query)
        messages = list(query.messages)
        if not messages and query.params.get("prompt"):
            messages = [{"role": "user", "content": str(query.params["prompt"])}]
        api_key = self.config.api_key or (os.environ.get(self.config.api_key_env) if self.config.api_key_env else "")
        if not api_key:
            return KernelResponse.error(
                LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                metadata={"reason": "api key not configured", "required_config": ["api_key_env"]},
            )
        if not self.config.hostname:
            return KernelResponse.error(
                LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                metadata={"reason": "base_url not configured", "required_config": ["base_url"]},
            )

        payload = {
            "model": self.config.model or self.config.name,
            "messages": messages,
            **query.params,
        }
        payload.pop("prompt", None)
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
            return KernelResponse(False, error_code=LLMCoreErrorCode.PROVIDER_ERROR, metadata={"reason": str(exc)})
        except json.JSONDecodeError as exc:
            return KernelResponse(False, error_code=LLMCoreErrorCode.RESPONSE_INVALID, metadata={"reason": str(exc)})

        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            return KernelResponse(False, error_code=LLMCoreErrorCode.RESPONSE_INVALID, metadata={"reason": str(exc)})
        normalized = normalize_openai_response(body)
        return KernelResponse(True, response_message=normalized.to_dict(), metadata={"provider": self.config.name})

    def embed(self, query: LLMQuery) -> KernelResponse:
        api_key = self.config.api_key or (os.environ.get(self.config.api_key_env) if self.config.api_key_env else "")
        if not api_key:
            return KernelResponse.error(
                LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                metadata={"reason": "api key not configured", "required_config": ["api_key_env"]},
            )
        if not self.config.hostname:
            return KernelResponse.error(
                LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                metadata={"reason": "base_url not configured", "required_config": ["base_url"]},
            )
        inputs = query.params.get("input", query.params.get("texts", query.params.get("text", "")))
        payload = {"model": self.config.model or self.config.name, "input": inputs}
        request = urllib.request.Request(
            f"{self.config.hostname.rstrip('/')}/embeddings",
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
            return KernelResponse.error(LLMCoreErrorCode.PROVIDER_ERROR, metadata={"reason": str(exc)})
        except json.JSONDecodeError as exc:
            return KernelResponse.error(LLMCoreErrorCode.RESPONSE_INVALID, metadata={"reason": str(exc)})
        embeddings = [item.get("embedding") for item in body.get("data", []) if isinstance(item, dict)]
        if not embeddings:
            return KernelResponse.error(LLMCoreErrorCode.RESPONSE_INVALID, metadata={"reason": "missing embeddings"})
        return KernelResponse.ok({"embeddings": embeddings, "model": body.get("model", self.config.model or self.config.name)})


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
            return KernelResponse.error(LLMCoreErrorCode.PROVIDER_ERROR, metadata={"reason": str(exc)})
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
        return KernelResponse.error(
            LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
            metadata={"backend": self.config.backend, "reason": "local HuggingFace generation pipeline is not configured"},
        )
