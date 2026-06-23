from __future__ import annotations

from pathlib import Path


REQUIRED_DOCS = [
    "kernel_syscalls.md",
    "runtime_real_only.md",
    "provider_contracts.md",
    "access_audit.md",
    "real_integration.md",
    "errors.md",
]


def test_real_only_foundation_docs_exist(runtime_src: Path):
    for name in REQUIRED_DOCS:
        path = runtime_src / "docs" / name
        assert path.exists(), name
        assert path.read_text(encoding="utf-8").strip(), name


def test_provider_docs_do_not_claim_reserved_modes_available(runtime_src: Path):
    docs = (runtime_src / "docs" / "provider_contracts.md").read_text(encoding="utf-8")

    assert "| ROS bridge | `cli` when `ros2` CLI is present |" in docs
    assert "`http`" in docs and "`websocket`" in docs
    assert "only when configured" in docs
    assert "`semantic_vector`" in docs
    assert "available" not in docs.split("| ROS bridge |", 1)[1].split("\n", 1)[0].lower()


def test_runtime_docs_state_no_simulated_runtime_surface(runtime_src: Path):
    docs = (runtime_src / "docs" / "runtime_real_only.md").read_text(encoding="utf-8").lower()

    assert "do not provide a" in docs
    assert "simulated runtime mode" in docs
    assert "task_input_field_unsupported" in docs
