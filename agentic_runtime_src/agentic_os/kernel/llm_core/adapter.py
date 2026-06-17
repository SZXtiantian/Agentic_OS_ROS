from __future__ import annotations

from typing import Any

from agentic_os.kernel.system_call import KernelResponse, KernelSyscall, LLMQuery

from .errors import LLMCoreErrorCode
from .local import LocalBackendProvider
from .provider import LLMProvider, MockLLMProvider, OpenAICompatibleProvider, UnsupportedLLMProvider
from .routing import SequentialRouting, SmartRouting
from .schema import LLMConfig
from .utils import normalize_llm_configs


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

    def complete(self, query: LLMQuery) -> KernelResponse:
        candidates = self.router.candidates(selected_llms=query.selected_llms, capability=query.action_type)
        if not candidates:
            return KernelResponse(False, error_code=LLMCoreErrorCode.MODEL_NOT_FOUND)

        last_response: KernelResponse | None = None
        for config in candidates:
            provider = self._provider_for(config)
            response = provider.complete(query)
            if response.success:
                response.metadata.setdefault("model", config.name)
                return response
            last_response = response
        return last_response or KernelResponse(False, error_code=LLMCoreErrorCode.MODEL_NOT_FOUND)

    def _provider_for(self, config: LLMConfig) -> LLMProvider:
        if config.name in self.providers:
            return self.providers[config.name]
        if config.backend in self.providers:
            return self.providers[config.backend]
        if config.backend == "mock":
            return MockLLMProvider(config)
        if config.backend in {"openai_compatible", "ollama_openai_compatible", "vllm_openai_compatible"}:
            return OpenAICompatibleProvider(config)
        if config.backend in {"huggingface", "hflocal", "vllm"}:
            return LocalBackendProvider(config)
        return UnsupportedLLMProvider(config)


def response_text(response: KernelResponse) -> str:
    message: Any = response.response_message
    if isinstance(message, dict):
        return str(message.get("content") or message.get("text") or message)
    return str(message or "")
