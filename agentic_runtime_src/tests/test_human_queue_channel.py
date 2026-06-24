from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agentic_os.kernel.access import AlwaysAllowTestInterventionProvider
from agentic_runtime.human_channel import FileHumanQueueChannel
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server
from agentic_runtime.types import AppManifest


async def _wait_for_request(path: Path, correlation_id: str, timeout_s: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if path.exists() and correlation_id in path.read_text(encoding="utf-8"):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"human request not written: {correlation_id}")


def test_human_queue_times_out_without_auto_answer(tmp_path):
    channel = FileHumanQueueChannel(tmp_path / "human", poll_interval_s=0.01)

    async def run():
        return await channel.ask(
            question="Approve?",
            timeout_s=0.03,
            app_id="agent_a",
            session_id="sess_human",
            correlation_id="human_timeout",
        )

    result = asyncio.run(run())

    assert result["success"] is False
    assert result["answered"] is False
    assert result["error_code"] == "HUMAN_OPERATOR_TIMEOUT"
    assert "human_timeout" in channel.paths.requests.read_text(encoding="utf-8")
    assert not channel.paths.responses.exists()
    assert channel.status()["pending_count"] == 0


def test_human_queue_accepts_external_response(tmp_path):
    channel = FileHumanQueueChannel(tmp_path / "human", poll_interval_s=0.01)

    async def run():
        task = asyncio.create_task(
            channel.ask(
                question="Approve?",
                timeout_s=1,
                app_id="agent_a",
                session_id="sess_human",
                correlation_id="human_answer",
            )
        )
        await _wait_for_request(channel.paths.requests, "human_answer")
        channel.record_response("human_answer", "yes", operator_id="operator_a")
        return await task

    result = asyncio.run(run())

    assert result["success"] is True
    assert result["answered"] is True
    assert result["answer"] == "yes"
    assert result["correlation_id"] == "human_answer"
    assert channel.status()["pending_count"] == 0
    response = json.loads(channel.paths.responses.read_text(encoding="utf-8").splitlines()[-1])
    assert response["operator_id"] == "operator_a"


def test_human_queue_cancel_returns_stable_codes(tmp_path):
    channel = FileHumanQueueChannel(tmp_path / "human", poll_interval_s=0.01)

    async def run():
        task = asyncio.create_task(
            channel.ask(
                question="Approve?",
                timeout_s=1,
                app_id="agent_a",
                session_id="sess_human",
                correlation_id="human_cancel",
            )
        )
        await _wait_for_request(channel.paths.requests, "human_cancel")
        cancel = channel.cancel("human_cancel")
        result = await task
        missing = channel.cancel("missing")
        return cancel, result, missing

    cancel, result, missing = asyncio.run(run())

    assert cancel["success"] is True
    assert result["success"] is False
    assert result["error_code"] == "HUMAN_CANCELLED"
    assert missing["success"] is False
    assert missing["error_code"] == "SYSCALL_NOT_FOUND"
    assert channel.status()["pending_count"] == 0


def test_runtime_human_skill_uses_real_queue_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("AGENTIC_SESSION_ROOT", str(tmp_path / "var" / "sessions"))
    server = create_test_runtime_server()
    app = AppManifest(
        name="human_queue_app",
        version="0",
        description="",
        entrypoint="main:run",
        permissions=["human.ask"],
        required_capabilities=["human.ask"],
    )
    server.kernel_service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()

    async def run():
        task = asyncio.create_task(
            server.executor.execute(
                app,
                "human.ask",
                {"question": "Approve?", "timeout_s": 1, "correlation_id": "runtime_human_answer"},
                "sess_runtime_human",
            )
        )
        await _wait_for_request(server.human_channel.paths.requests, "runtime_human_answer")
        server.human_channel.record_response("runtime_human_answer", "yes")
        return await task

    result = asyncio.run(run())

    assert result.success is True
    assert result.data["answer"] == "yes"
    assert result.data["correlation_id"] == "runtime_human_answer"
    audit = server.audit_logger.recent(limit=1)[0]
    assert audit["skill_name"] == "human.ask"
    assert audit["backend"] == "runtime_human_queue"


def test_runtime_human_skill_uses_call_id_as_queue_correlation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("AGENTIC_SESSION_ROOT", str(tmp_path / "var" / "sessions"))
    server = create_test_runtime_server()
    app = AppManifest(
        name="human_queue_app",
        version="0",
        description="",
        entrypoint="main:run",
        permissions=["human.ask"],
        required_capabilities=["human.ask"],
    )
    server.kernel_service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()

    async def run():
        task = asyncio.create_task(
            server.executor.execute(
                app,
                "human.ask",
                {"question": "Approve?", "timeout_s": 1},
                "sess_runtime_human",
                call_id="human_call_1",
            )
        )
        await _wait_for_request(server.human_channel.paths.requests, "human_call_1")
        cancel = server.human_channel.cancel("human_call_1", session_id="sess_runtime_human")
        result = await task
        return cancel, result

    cancel, result = asyncio.run(run())

    assert cancel["success"] is True
    assert result.success is False
    assert result.error_code == "HUMAN_CANCELLED"
    assert result.data["correlation_id"] == "human_call_1"
    audit = server.audit_logger.recent(limit=1)[0]
    assert audit["status"] == "cancelled"
