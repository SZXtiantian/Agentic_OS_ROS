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


def test_hello_world_bare_kernel_records_real_syscall_metadata(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    class Executor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("hello_world_agent must use kernel syscalls in this smoke")

    async def scenario():
        service.start()
        try:
            app = AppManifest(
                "hello_world_agent",
                "0.1.0",
                "",
                "main:run",
                [
                    "report.say",
                    "context.write",
                    "context.read",
                    "tool.execute.calculator.add",
                    "memory.write",
                    "memory.read",
                    "storage.write",
                    "storage.read",
                ],
                [],
            )
            ctx = AgentContext(Executor(), app, "sess_hello")
            return await _load_run()(ctx, message="hello kernel smoke")
        finally:
            service.stop()

    result = asyncio.run(scenario())

    assert result["schema_version"] == "1.0"
    assert result["success"] is False
    assert result["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["context_put"]["success"] is True
    assert by_name["context_get"]["success"] is True
    assert by_name["memory_remember"]["success"] is True
    assert by_name["storage_write"]["success"] is True
    assert by_name["tool_calculator_add"]["success"] is True
    assert by_name["skill_report_say"]["success"] is False
    assert by_name["skill_report_say"]["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    assert result["syscall_ids"]
    assert all(isinstance(syscall_id, str) and syscall_id for syscall_id in result["syscall_ids"])


def _load_run():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("hello_world_agent_main", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run
