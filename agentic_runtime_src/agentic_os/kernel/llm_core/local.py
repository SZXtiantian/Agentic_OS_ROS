from __future__ import annotations

from agentic_os.kernel.system_call import KernelResponse, LLMQuery

from .errors import LLMCoreErrorCode
from .schema import LLMConfig


class LocalBackendProvider:
    """Shell for optional local model backends such as vLLM or HuggingFace."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, query: LLMQuery) -> KernelResponse:
        model = str(self.config.model or "").strip()
        if not model:
            return KernelResponse.error(
                LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                metadata={"backend": self.config.backend, "reason": "model not configured", "required_config": ["model"]},
            )
        return KernelResponse(
            False,
            error_code=LLMCoreErrorCode.PROVIDER_UNSUPPORTED,
            metadata={"backend": self.config.backend, "model": model, "reason": "local LLM backend is reserved, not available"},
        )
