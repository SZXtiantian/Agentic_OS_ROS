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
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


class RecordingLLMChat:
    def __init__(self):
        self.calls: list[dict[str, str]] = []

    def chat_json(self, *, system_prompt: str, user_prompt: str):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return {
            "schema_version": "1.0",
            "planner_mode": "llm",
            "greeting": "Hello from Agentic OS.",
            "report_message": "Hello World plan executed through Agentic OS Runtime LLM.",
            "memory_key": "hello_world:last_plan",
            "storage_path": "hello_world/last_plan.json",
            "tool_args": {"a": 2, "b": 3},
            "user_summary": "Greet the user and exercise kernel surfaces.",
        }


def test_hello_world_requires_runtime_llm_facade(tmp_path):
    result, llm_chat = asyncio.run(_run_bare_kernel(tmp_path, llm_chat=None, message="hello kernel smoke"))

    assert llm_chat is None
    assert result["schema_version"] == "1.0"
    assert result["success"] is False
    assert result["error_code"] == "LLMCHAT_UNAVAILABLE"
    assert result["planner_mode"] == ""
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["llm_plan"]["success"] is False
    assert "context_put" not in by_name


def test_hello_world_injected_runtime_llm_plan_executes_kernel_steps(tmp_path):
    result, llm_chat = asyncio.run(_run_bare_kernel(tmp_path, llm_chat=RecordingLLMChat(), message="hello kernel smoke"))

    assert llm_chat is not None
    assert llm_chat.calls
    assert "hello kernel smoke" in llm_chat.calls[0]["user_prompt"]
    assert result["success"] is False
    assert result["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    assert result["planner_mode"] == "llm"
    assert result["plan"]["planner_mode"] == "llm"
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["llm_plan"]["success"] is True
    assert by_name["context_put"]["success"] is True
    assert by_name["context_get"]["success"] is True
    assert by_name["memory_remember"]["success"] is True
    assert by_name["storage_write"]["success"] is True
    assert by_name["tool_calculator_add"]["success"] is True
    assert by_name["skill_report_say"]["success"] is False
    assert by_name["skill_report_say"]["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    assert result["syscall_ids"]
    assert all(isinstance(syscall_id, str) and syscall_id for syscall_id in result["syscall_ids"])


async def _run_bare_kernel(tmp_path, *, llm_chat, message: str):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))
    if llm_chat is not None:
        service.runtime_server = SimpleNamespace(llm_chat=llm_chat)

    class Executor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("hello_world_agent must use kernel syscalls in this smoke")

    service.start()
    try:
        app = AppManifest(
            "hello_world_agent",
            "0.1.0",
            "",
            "main:run",
            [
                "llm.external.call",
                "report.say",
                "context.write",
                "context.read",
                "tool.execute.calculator.add",
                "memory.write",
                "memory.read",
                "storage.write",
                "storage.read",
            ],
            ["agenticos.runtime.llm_chat", "llm.chat"],
        )
        ctx = AgentContext(Executor(), app, "sess_hello")
        return await _load_run()(ctx, message=message), llm_chat
    finally:
        service.stop()


def _load_run():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("hello_world_agent_main", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run
