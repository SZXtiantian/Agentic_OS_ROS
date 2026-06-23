from __future__ import annotations

from types import SimpleNamespace

from agentic_os.kernel.llm_core import LLMAdapter, LLMConfig
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.provider_contracts import validate_mode_truth


PROVIDER_KEYS = {"ros_bridge", "llm", "human", "context", "memory", "storage", "tool", "skill"}


def test_kernel_status_exposes_provider_contract_for_all_namespaces(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    status = service.status()
    providers = status["providers"]

    assert providers["contract"] == "capability_truth_v1"
    assert PROVIDER_KEYS.issubset(providers)
    for name in PROVIDER_KEYS:
        provider = providers[name]
        for field in providers["required_fields"]:
            assert field in provider, f"{name} missing {field}"
        assert "implemented_modes" in provider
        assert "available_modes" in provider
        assert "unsupported_modes" in provider
        assert "reserved_modes" in provider


def test_provider_available_modes_are_implemented_and_not_reserved(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    providers = service.status()["providers"]

    for name in PROVIDER_KEYS:
        provider = providers[name]
        validate_mode_truth(
            available_modes=provider["available_modes"],
            implemented_modes=provider["implemented_modes"],
            unsupported_modes=provider["unsupported_modes"],
            reserved_modes=provider["reserved_modes"],
        )


def test_bare_kernel_skill_provider_does_not_claim_runtime_backend_available(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    skill = service.status()["providers"]["skill"]

    assert skill["status"] == "unavailable"
    assert skill["health"] == "unavailable"
    assert skill["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    assert skill["available_modes"] == []


def test_llm_available_modes_require_real_configuration():
    unconfigured = LLMAdapter([LLMConfig(name="missing", backend="openai_compatible")]).status()
    configured = LLMAdapter(
        [
            LLMConfig(
                name="configured",
                backend="openai_compatible",
                hostname="http://127.0.0.1:9/v1",
                api_key="local-test-key",
                model="chat-model",
            )
        ]
    ).status()

    assert unconfigured["available_modes"] == []
    assert configured["available_modes"] == ["openai_compatible"]
