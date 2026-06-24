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


def test_color_block_rejects_invalid_color_with_stable_error(tmp_path):
    result = asyncio.run(_run_bare_kernel(tmp_path, color="purple", require_confirmation=False))

    assert result["success"] is False
    assert result["error_code"] == "COLOR_BLOCK_COLOR_NOT_ALLOWED"
    assert result["missing"] == []
    assert result["next_action"]


def test_color_block_missing_runtime_backend_is_not_success(tmp_path):
    result = asyncio.run(_run_bare_kernel(tmp_path, color="red", require_confirmation=False))

    assert result["success"] is False
    assert result["error_code"] == "UNVERIFIED_REAL_DEPENDENCY"
    assert "robot.get_state" in result["missing"]
    assert result["report_error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["check_robot"]["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    assert by_name["write_result"]["success"] is True
    assert result["syscall_ids"]


async def _run_bare_kernel(tmp_path, **kwargs):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    class Executor:
        kernel_service = service

        async def execute(self, *args, **execute_kwargs):
            raise AssertionError("color_block_grasper_agent must use kernel skill syscalls")

    service.start()
    try:
        app = AppManifest(
            "color_block_grasper_agent",
            "0.1.0",
            "",
            "main:run",
            [
                "robot.state.read",
                "arm.state.read",
                "human.ask",
                "perception.detect.color_block",
                "perception.capture",
                "manipulation.pick.color_block",
                "manipulation.place.color_block",
                "memory.write",
                "storage.write",
                "storage.read",
                "report.say",
            ],
            [],
        )
        ctx = AgentContext(Executor(), app, "sess_color")
        return await _load_run()(ctx, **kwargs)
    finally:
        service.stop()


def _load_run():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("color_block_grasper_agent_main", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run
