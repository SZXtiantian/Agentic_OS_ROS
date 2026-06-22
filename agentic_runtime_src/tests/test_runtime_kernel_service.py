from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

from agentic_os.kernel.scheduler import RoundRobinKernelScheduler
from agentic_os.kernel.system_call import LLMQuery, MemoryQuery, ToolQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.server import RuntimeServer
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest, SkillResult


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


def make_kernel_config(tmp_path, kernel):
    return SimpleNamespace(
        repo_root=tmp_path,
        storage_root=tmp_path / "storage",
        tool_root=tmp_path / "tools",
        scheduler_policy="fifo",
        kernel=kernel,
    )


def make_app() -> AppManifest:
    return AppManifest(
        name="kernel_test_app",
        version="0",
        description="",
        entrypoint="main:run",
        permissions=["robot.move"],
        required_capabilities=[],
    )


class _OpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.path.endswith("/chat/completions"):
            messages = body.get("messages") or [{"content": "ok"}]
            content = messages[-1].get("content", "ok")
            payload = {"choices": [{"message": {"role": "assistant", "content": f"ack: {content}"}}]}
        elif self.path.endswith("/embeddings"):
            inputs = body.get("input", [])
            if isinstance(inputs, str):
                inputs = [inputs]
            payload = {"model": body.get("model", "embedding"), "data": [{"embedding": [float(len(str(item))), 1.0]} for item in inputs]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        return


def openai_config(tmp_path):
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    server = HTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = make_kernel_config(
        tmp_path,
        {
            "llm": {
                "configs": [
                    {
                        "name": "local-openai",
                        "backend": "openai_compatible",
                        "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                        "api_key": "test-key",
                        "model": "local-chat",
                        "capabilities": ["chat", "complete", "embed"],
                    }
                ]
            }
        },
    )
    return server, config


def test_kernel_service_starts_and_stops_scheduler(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    service.start()
    assert service.status()["scheduler"]["active"] is True

    service.stop()
    assert service.status()["scheduler"]["active"] is False


def test_kernel_service_executes_llm_query(tmp_path):
    server, config = openai_config(tmp_path)
    service = KernelService(config=config)
    service.start()
    try:
        result = service.execute_request("agent_a", LLMQuery(operation_type="chat"), timeout_s=1.0)
    finally:
        service.stop()
        server.shutdown()

    assert result.success is True
    assert result.metadata["queue_name"] == "llm"


def test_kernel_service_default_config_reports_llm_unavailable(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    status = service.status()

    assert status["config"]["llm"]["configs"][0]["name"] == "unconfigured"
    assert status["config"]["llm"]["configs"][0]["backend"] == "openai_compatible"
    assert status["llm"]["state"] == "unavailable"
    assert status["llm"]["providers"][0]["error_code"] == "LLM_PROVIDER_UNCONFIGURED"


def test_kernel_service_uses_rr_scheduler_from_kernel_config(tmp_path):
    service = KernelService(config=make_kernel_config(tmp_path, {"scheduler_policy": "rr"}))

    assert isinstance(service.scheduler, RoundRobinKernelScheduler)


def test_kernel_service_uses_configured_llm_without_status_secret_leak(tmp_path):
    service = KernelService(
        config=make_kernel_config(
            tmp_path,
            {
                "llm": {
                    "routing_strategy": "sequential",
                    "configs": [
                        {
                            "name": "configured-openai",
                            "backend": "openai_compatible",
                            "enabled": True,
                            "api_key": "super-secret",
                            "base_url": "https://example.test/v1",
                            "capabilities": ["chat", "json"],
                        }
                    ],
                }
            },
        )
    )

    status = service.status()
    rendered = str(status)

    assert status["config"]["llm"]["configs"][0]["name"] == "configured-openai"
    assert "super-secret" not in rendered
    assert "api_key" not in rendered


def test_kernel_service_execute_request_lazily_starts_scheduler(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    try:
        result = service.execute_request("agent_a", LLMQuery(operation_type="chat"), timeout_s=1.0)
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "LLM_PROVIDER_UNCONFIGURED"
    assert status["scheduler"]["active"] is True
    assert status["scheduler"]["threads"]


def test_kernel_service_executes_memory_query(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            MemoryQuery(operation_type="remember", params={"memory_id": "x", "content": "hello"}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert result.success is True


def test_robot_skill_not_routed_to_generic_tool(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            ToolQuery(operation_type="call_tool", params={"name": "robot.navigate_to", "args": {"place": "kitchen"}}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"


def test_sdk_kernel_llm_chat_uses_kernel_service(tmp_path):
    server, config = openai_config(tmp_path)
    service = KernelService(config=config)

    class FakeExecutor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("skill executor should not be used")

    async def run():
        service.start()
        try:
            ctx = AgentContext(FakeExecutor(), make_app(), "sess_1")
            result = await ctx.kernel.llm.chat(messages=[{"role": "user", "content": "hi"}], timeout_s=1.0)
            assert result.success is True
            assert result.metadata["queue_name"] == "llm"
        finally:
            service.stop()
            server.shutdown()

    asyncio.run(run())


def test_call_skill_still_uses_skill_executor():
    class FakeExecutor:
        kernel_service = None

        async def execute(self, app, name, args, session_id):
            return SkillResult(True, data={"skill": name, "args": args, "session_id": session_id})

    async def run():
        ctx = AgentContext(FakeExecutor(), make_app(), "sess_skill")
        result = await ctx.call_skill("robot.navigate_to", {"place": "kitchen"})
        assert result.data["skill"] == "robot.navigate_to"
        assert result.data["session_id"] == "sess_skill"

    asyncio.run(run())


def test_runtime_server_shutdown_stops_kernel_scheduler(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    server = RuntimeServer.create(mock=True)

    server.kernel_service.start()
    assert server.kernel_service.status()["scheduler"]["active"] is True
    server.shutdown()

    assert server.kernel_service.status()["scheduler"]["active"] is False
    assert server.kernel_service.status()["scheduler"]["threads"] == {}
