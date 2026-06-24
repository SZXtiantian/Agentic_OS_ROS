from __future__ import annotations

import asyncio

from agentic_runtime.human_channel import FileHumanQueueChannel
from agentic_runtime.provider_contracts import human_operator_contract, validate_mode_truth


def test_human_file_queue_is_only_available_real_mode(tmp_path):
    channel = FileHumanQueueChannel(tmp_path / "human")
    status = channel.status()
    contract = human_operator_contract(status)

    validate_mode_truth(
        available_modes=contract["available_modes"],
        implemented_modes=contract["implemented_modes"],
        unsupported_modes=contract["unsupported_modes"],
        reserved_modes=contract["reserved_modes"],
    )
    assert contract["available_modes"] == ["file_queue"]
    assert "console" in contract["reserved_modes"]
    assert "http" in contract["reserved_modes"]
    assert "websocket" in contract["reserved_modes"]


def test_human_queue_timeout_does_not_auto_answer(tmp_path):
    channel = FileHumanQueueChannel(tmp_path / "human", poll_interval_s=0.01)

    async def run():
        return await channel.ask(question="Approve?", timeout_s=0.02, correlation_id="no_auto_answer")

    result = asyncio.run(run())

    assert result["success"] is False
    assert result["answered"] is False
    assert result["answer"] == ""
    assert result["error_code"] == "HUMAN_OPERATOR_TIMEOUT"
