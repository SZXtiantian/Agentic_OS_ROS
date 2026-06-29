from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

RUNTIME_SRC = Path(__file__).resolve().parents[3] / "agentic_runtime_src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from agentic_runtime.kernel_service import KernelService
from agentic_runtime.server import RuntimeServer
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


def test_app_template_uses_real_kernel_syscalls(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    class Executor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("app_template smoke must use kernel syscalls")

    async def scenario():
        service.start()
        try:
            app = AppManifest(
                "app_template",
                "0.1.0",
                "",
                "main:run",
                ["report.say", "tool.execute.calculator.add", "memory.write", "memory.read", "storage.write", "storage.read"],
                [],
            )
            session_id = "sess_template"
            agent = service.create_agent(
                app_id=app.name,
                session_id=session_id,
                agent_name=app.name,
                agent_id="agent_app_template_smoke",
            )
            start = service.start_agent(agent.agent_id)
            assert start.success
            ctx = AgentContext(Executor(), app, session_id, agent_id=agent.agent_id)
            result = await _load_run()(ctx, message="template smoke")
        finally:
            service.stop()
        return result

    result = asyncio.run(scenario())

    assert result["success"] is False
    assert result["results"]["context_put"]["success"] is True
    assert result["results"]["context_get"]["success"] is True
    assert result["results"]["memory"]["success"] is True
    assert result["results"]["storage"]["success"] is True
    assert result["results"]["tool"]["success"] is True
    assert result["results"]["report"]["error_code"] == "SKILL_BACKEND_UNAVAILABLE"


def test_app_template_real_runtime_smoke_succeeds(tmp_path, monkeypatch):
    report_log = tmp_path / "reports" / "report.jsonl"
    config_path = tmp_path / "runtime.yaml"
    repo_root = RUNTIME_SRC.parent
    app_root = repo_root / "agentic_apps"
    config_path.write_text(
        "\n".join(
            [
                "runtime:",
                f"  audit_log_path: {tmp_path / 'audit' / 'audit.jsonl'}",
                f"  memory_db_path: {tmp_path / 'memory' / 'memory.sqlite3'}",
                "  default_skill_timeout_s: 60",
                f"  app_root: {app_root}",
                f"  skill_root: {RUNTIME_SRC / 'skills'}",
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
        return await server.scheduler.run_app("app_template", message="real runtime smoke")

    result = asyncio.run(scenario())

    assert result["status"] == "completed"
    assert result["result"]["success"] is True
    assert result["result"]["results"]["report"]["success"] is True
    assert report_log.exists()


def _load_run():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("app_template_main", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run
