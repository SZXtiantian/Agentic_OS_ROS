from __future__ import annotations

from pathlib import Path


def test_provider_docs_classify_unimplemented_modes_as_reserved_or_unsupported(runtime_src: Path):
    docs = (runtime_src / "docs" / "provider_contracts.md").read_text(encoding="utf-8")

    ros_row = next(line for line in docs.splitlines() if line.startswith("| ROS bridge |"))
    human_row = next(line for line in docs.splitlines() if line.startswith("| Human |"))
    llm_row = next(line for line in docs.splitlines() if line.startswith("| LLM |"))

    assert "`cli`" in ros_row
    for mode in ("`service`", "`action`", "`topic`", "`http`", "`websocket`"):
        assert mode in ros_row.split("|")[-2]
    assert "`file_queue`" in human_row
    assert "`console`" in human_row.split("|")[-2]
    assert "`local`" in llm_row.split("|")[-2]
    assert "`huggingface`" in llm_row.split("|")[-2]


def test_real_integration_docs_use_unverified_dependency_language(runtime_src: Path):
    docs = (runtime_src / "docs" / "real_integration.md").read_text(encoding="utf-8")

    assert "UNVERIFIED_REAL_DEPENDENCY" in docs
    assert "must not be replaced by simulated success" in docs
