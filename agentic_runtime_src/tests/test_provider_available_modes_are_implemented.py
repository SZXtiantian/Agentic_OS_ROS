from __future__ import annotations

from types import SimpleNamespace

from agentic_runtime.kernel_service import KernelService
from agentic_runtime.provider_contracts import validate_mode_truth


def test_all_provider_available_modes_are_implemented(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))
    providers = service.status()["providers"]

    for name, provider in providers.items():
        if name in {"contract", "required_fields"}:
            continue
        validate_mode_truth(
            available_modes=provider["available_modes"],
            implemented_modes=provider["implemented_modes"],
            unsupported_modes=provider["unsupported_modes"],
            reserved_modes=provider["reserved_modes"],
        )
