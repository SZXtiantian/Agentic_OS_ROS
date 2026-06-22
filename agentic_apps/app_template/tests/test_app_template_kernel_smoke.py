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
            ctx = AgentContext(Executor(), app, "sess_template")
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


def _load_run():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("app_template_main", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run
