from __future__ import annotations

from typing import Any

from agentic_os.kernel.context import GenerationSnapshot
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall, LLMQuery

from .errors import LLMCoreErrorCode
from .local import LocalBackendProvider
from .provider import (
    HuggingFaceProvider,
    LiteLLMProvider,
    LLMProvider,
    MockLLMProvider,
    OpenAICompatibleProvider,
    UnsupportedLLMProvider,
    VLLMOpenAIProvider,
)
from .routing import SequentialRouting, SmartRouting
from .schema import LLMConfig
from .utils import enforce_json_response, normalize_llm_configs


class LLMAdapter:
    def __init__(
        self,
        llm_configs: list[LLMConfig | dict],
        routing_strategy: str = "sequential",
        providers: dict[str, LLMProvider] | None = None,
    ) -> None:
        self.llm_configs = normalize_llm_configs(llm_configs)
        self.providers = dict(providers or {})
        if routing_strategy == "smart":
            self.router = SmartRouting(self.llm_configs)
        else:
            self.router = SequentialRouting(self.llm_configs)

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        query = getattr(syscall, "query", None)
        if not isinstance(query, LLMQuery):
            query = LLMQuery(
                operation_type=syscall.operation_type,
                params=dict(syscall.params),
                messages=list(syscall.params.get("messages") or []),
                tools=syscall.params.get("tools"),
                selected_llms=syscall.params.get("selected_llms"),
                response_format=syscall.params.get("response_format"),
                action_type=str(syscall.params.get("action_type", "chat")),
            )
        return self.complete(query)

    def address_batch(self, syscalls: list[KernelSyscall]) -> list[KernelResponse]:
        queries: list[LLMQuery] = []
        for syscall in syscalls:
            query = getattr(syscall, "query", None)
            if not isinstance(query, LLMQuery):
                query = LLMQuery(
                    operation_type=syscall.operation_type,
                    params=dict(syscall.params),
                    messages=list(syscall.params.get("messages") or []),
                    tools=syscall.params.get("tools"),
                    selected_llms=syscall.params.get("selected_llms"),
                    response_format=syscall.params.get("response_format"),
                    action_type=str(syscall.params.get("action_type", "chat")),
                )
            queries.append(query)
        return self.complete_batch(queries)

    def complete(self, query: LLMQuery) -> KernelResponse:
        candidates = self.router.candidates(selected_llms=query.selected_llms, capability=query.action_type)
        if not candidates:
            return KernelResponse(False, error_code=LLMCoreErrorCode.MODEL_NOT_FOUND)

        last_response: KernelResponse | None = None
        for config in candidates:
            provider = self._provider_for(config)
            response = enforce_json_response(query.response_format, provider.complete(query))
            if response.success:
                response.metadata.setdefault("model", config.name)
                return response
            last_response = response
        final = last_response or KernelResponse(False, error_code=LLMCoreErrorCode.MODEL_NOT_FOUND)
        final.metadata.setdefault("candidates", [config.name for config in candidates])
        return final

    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        if not queries:
            return []
        candidates = self.router.candidates(selected_llms=queries[0].selected_llms, capability=queries[0].action_type)
        if not candidates:
            return [KernelResponse.error(LLMCoreErrorCode.MODEL_NOT_FOUND) for _ in queries]

        last_responses: list[KernelResponse] | None = None
        for config in candidates:
            provider = self._provider_for(config)
            if hasattr(provider, "complete_batch"):
                responses = list(provider.complete_batch(queries))
            else:
                responses = [provider.complete(query) for query in queries]
            for response in responses:
                response.metadata.setdefault("model", config.name)
            if any(response.success for response in responses):
                return _normalize_batch_length(responses, len(queries))
            last_responses = responses
        return _normalize_batch_length(
            last_responses or [KernelResponse.error(LLMCoreErrorCode.MODEL_NOT_FOUND) for _ in queries],
            len(queries),
        )

    def complete_with_time_slice(
        self,
        query: LLMQuery,
        time_slice_s: float,
        snapshot: GenerationSnapshot | None = None,
    ) -> tuple[KernelResponse, GenerationSnapshot | None]:
        candidates = self.router.candidates(selected_llms=query.selected_llms, capability=query.action_type)
        if not candidates:
            return KernelResponse.error(LLMCoreErrorCode.MODEL_NOT_FOUND), None
        config = candidates[0]
        provider = self._provider_for(config)
        if hasattr(provider, "complete_with_time_slice"):
            response, next_snapshot = provider.complete_with_time_slice(query, time_slice_s, snapshot)
            response.metadata.setdefault("model", config.name)
            return response, next_snapshot
        response = self.complete(query)
        response.metadata["non_preemptible_llm_call"] = True
        return response, None

    def _provider_for(self, config: LLMConfig) -> LLMProvider:
        if config.name in self.providers:
            return self.providers[config.name]
        if config.backend in self.providers:
            return self.providers[config.backend]
        if config.backend == "mock":
            return MockLLMProvider(config)
        if config.backend in {"litellm", "litellm_compatible"}:
            return LiteLLMProvider(config)
        if config.backend in {"openai_compatible", "ollama_openai_compatible", "vllm_openai_compatible"}:
            return OpenAICompatibleProvider(config)
        if config.backend in {"vllm"}:
            return VLLMOpenAIProvider(config)
        if config.backend in {"huggingface", "hf", "hflocal"}:
            return HuggingFaceProvider(config)
        if config.backend in {"local"}:
            return LocalBackendProvider(config)
        return UnsupportedLLMProvider(config)


def response_text(response: KernelResponse) -> str:
    message: Any = response.response_message
    if isinstance(message, dict):
        return str(message.get("content") or message.get("text") or message)
    return str(message or "")


def _normalize_batch_length(responses: list[KernelResponse], expected: int) -> list[KernelResponse]:
    if len(responses) >= expected:
        return responses[:expected]
    missing = [KernelResponse.error(LLMCoreErrorCode.RESPONSE_INVALID, metadata={"reason": "missing batch response"})]
    return responses + missing * (expected - len(responses))
