from __future__ import annotations

from agentic_os.kernel.llm_core import LLMAdapter, LLMConfig, LLMCoreErrorCode
from agentic_os.kernel.system_call import LLMQuery


def test_reserved_llm_backends_are_not_available_modes():
    status = LLMAdapter(
        [
            LLMConfig(name="hf", backend="huggingface", model="real-model"),
            LLMConfig(name="local", backend="local", model="real-model"),
        ]
    ).status()

    assert status["available_modes"] == []
    assert "huggingface" in status["reserved_modes"]
    assert "local" in status["reserved_modes"]
    assert status["contract"]["error_code"] in {
        LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING,
        LLMCoreErrorCode.PROVIDER_UNSUPPORTED,
        LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
    }


def test_unknown_llm_backend_returns_unsupported():
    response = LLMAdapter([LLMConfig(name="x", backend="unknown_backend")]).complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_UNSUPPORTED


def test_llm_status_exposes_truth_and_request_failure_fields():
    status = LLMAdapter([LLMConfig(name="missing", backend="openai_compatible")]).status()
    provider = status["providers"][0]

    for field in ("configured", "available", "healthy", "missing", "error_code", "request_failure_code"):
        assert field in status
        assert field in provider
    assert status["available"] is False
    assert status["request_failure_code"] == LLMCoreErrorCode.REQUEST_FAILED
    assert provider["error_code"] == LLMCoreErrorCode.PROVIDER_UNCONFIGURED
