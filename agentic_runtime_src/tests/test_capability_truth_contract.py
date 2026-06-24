from __future__ import annotations

from types import SimpleNamespace

from agentic_runtime.kernel_service import KernelService
from agentic_runtime.provider_contracts import TRUTH_STATUS_FIELDS, validate_mode_truth


EXPECTED_PROVIDERS = {"ros_bridge", "llm", "human", "context", "memory", "storage", "tool", "skill"}


def test_capability_truth_contract_fields_and_mode_sets(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))
    providers = service.status()["providers"]

    assert providers["contract"] == "capability_truth_v1"
    assert EXPECTED_PROVIDERS.issubset(providers)
    for name in EXPECTED_PROVIDERS:
        provider = providers[name]
        for field in TRUTH_STATUS_FIELDS:
            assert field in provider, f"{name} missing {field}"
        assert isinstance(provider["capability_evidence"], dict)
        validate_mode_truth(
            available_modes=provider["available_modes"],
            implemented_modes=provider["implemented_modes"],
            unsupported_modes=provider["unsupported_modes"],
            reserved_modes=provider["reserved_modes"],
        )


def test_capability_truth_violation_is_stable_error_surface():
    try:
        validate_mode_truth(
            available_modes=["reserved"],
            implemented_modes=["real"],
            unsupported_modes=[],
            reserved_modes=["reserved"],
        )
    except ValueError as exc:
        assert "available_modes" in str(exc)
    else:
        raise AssertionError("capability truth violation must fail")
