from __future__ import annotations

import asyncio
from pathlib import Path

from agentic_runtime.server import RuntimeServer


def test_hello_world_agent_real_runtime_report_succeeds(tmp_path, monkeypatch, repo_root: Path, runtime_src: Path):
    report_log = tmp_path / "reports" / "report.jsonl"
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        "\n".join(
            [
                "runtime:",
                f"  audit_log_path: {tmp_path / 'audit' / 'audit.jsonl'}",
                f"  memory_db_path: {tmp_path / 'memory' / 'memory.sqlite3'}",
                "  default_skill_timeout_s: 60",
                f"  app_root: {repo_root / 'agentic_apps'}",
                f"  skill_root: {runtime_src / 'skills'}",
                "  ros_bridge_mode: cli",
                "  daemon_host: 127.0.0.1",
                "  daemon_port: 8765",
                f"  session_root: {tmp_path / 'sessions'}",
                f"  storage_root: {tmp_path / 'storage'}",
                f"  context_root: {tmp_path / 'context'}",
                "  scheduler_policy: single_robot_fifo",
                "  memory_provider: sqlite",
                f"  tool_root: {tmp_path / 'tools'}",
                f"  bridge_root: {tmp_path / 'bridges'}",
                f"  bridge_profile_root: {tmp_path / 'profiles'}",
                "  enable_daemon_api: true",
                "kernel:",
                "  scheduler_policy: fifo",
                "  tool:",
                f"    tool_root: {tmp_path / 'tools'}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTIC_RUNTIME_CONFIG", str(config_path))
    monkeypatch.setenv("AGENTIC_REPORT_LOG", str(report_log))

    async def scenario():
        server = RuntimeServer.create()
        return await server.scheduler.run_app("hello_world_agent", message="real runtime hello")

    result = asyncio.run(scenario())

    assert result["status"] == "completed"
    assert result["result"]["success"] is True
    assert result["result"]["steps"][-1]["name"] == "skill_report_say"
    assert result["result"]["steps"][-1]["success"] is True
    assert result["result"]["audit_ids"]
    assert report_log.exists()
