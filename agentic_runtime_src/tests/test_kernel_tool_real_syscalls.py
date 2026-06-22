from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

from agentic_os.kernel.system_call import ToolQuery
from agentic_os.kernel.tool import ToolManager
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


def make_config(tmp_path):
    tool_root = tmp_path / "tools"
    tool_root.mkdir()
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tool_root)


def test_builtin_tools_execute_real_work(tmp_path):
    tool_root = tmp_path / "tools"
    tool_root.mkdir()
    digest_file = tool_root / "sample.txt"
    digest_file.write_text("hello", encoding="utf-8")
    manager = ToolManager(tool_root=tool_root)

    added = manager.call_tool("agent_a", "calculator.add", {"a": 2, "b": 3})
    report = manager.call_tool(
        "agent_a",
        "format_report.markdown",
        {"title": "Inspection", "sections": [{"heading": "Result", "body": "ok"}]},
    )
    digest = manager.call_tool("agent_a", "file_digest.sha256", {"path": "sample.txt"})
    listed = manager.address_request(SimpleNamespace(agent_name="agent_a", operation_type="tool_list", params={}))

    assert added["result"] == {"value": 5}
    assert "# Inspection" in report["result"]["markdown"]
    assert digest["result"]["sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert any(tool["tool"] == "calculator.add" for tool in listed["tools"])


def test_tool_describe_status_and_cancel_are_stable(tmp_path):
    manager = ToolManager(tool_root=tmp_path / "tools")

    described = manager.address_request(
        SimpleNamespace(agent_name="agent_a", operation_type="tool_describe", params={"name": "calculator.add"})
    )
    status = manager.address_request(SimpleNamespace(agent_name="agent_a", operation_type="tool_status", params={}))
    cancel = manager.address_request(SimpleNamespace(agent_name="agent_a", operation_type="tool_cancel", params={"call_id": "x"}))

    assert described["success"] is True
    assert described["builtin"] is True
    assert status["status"]["registered"]
    assert cancel["success"] is False
    assert cancel["error_code"] == "TOOL_CANCEL_UNSUPPORTED"


def test_kernel_tool_builtin_call_requires_permission_and_succeeds_with_permission(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        denied = service.execute_request(
            "agent_a",
            ToolQuery(operation_type="tool_call", params={"name": "calculator.add", "args": {"a": 1, "b": 2}}),
            timeout_s=1.0,
        )
        allowed = service.execute_request(
            "agent_a",
            ToolQuery(
                operation_type="tool_call",
                params={
                    "name": "calculator.add",
                    "args": {"a": 1, "b": 2},
                    "permissions": ["tool.execute.calculator.add"],
                },
            ),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert denied.success is False
    assert denied.error_code == "ACCESS_DENIED"
    assert allowed.success is True
    assert allowed.response.data["result"] == {"value": 3}
    assert allowed.metadata["queue_name"] == "tool"


def test_tool_load_unload_register_builtin_require_intervention(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    manifest = service.tool.tool_root / "sample.yaml"
    manifest.write_text("name: sample.tool\nentrypoint: sample:run\n", encoding="utf-8")
    service.start()
    try:
        loaded = service.execute_request(
            "agent_a",
            ToolQuery(operation_type="tool_load_manifest", params={"path": str(manifest)}),
            timeout_s=1.0,
        )
        unloaded = service.execute_request(
            "agent_a",
            ToolQuery(operation_type="tool_unload", params={"name": "calculator.add"}),
            timeout_s=1.0,
        )
        registered = service.execute_request(
            "agent_a",
            ToolQuery(operation_type="tool_register_builtin", params={"name": "calculator.add"}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert loaded.success is False
    assert loaded.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert unloaded.success is False
    assert unloaded.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert registered.success is False
    assert registered.error_code == "ACCESS_INTERVENTION_REQUIRED"


def test_kernel_tool_sdk_permissions_from_manifest(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    class Executor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("tool SDK must use kernel service")

    async def run():
        service.start()
        try:
            app = AppManifest("tool_sdk_app", "0", "", "main:run", ["tool.execute.calculator.add"], [])
            ctx = AgentContext(Executor(), app, "sess_tool")
            result = await ctx.kernel.tool.call("calculator.add", {"a": 4, "b": 6}, timeout_s=1.0)
            described = await ctx.kernel.tool.describe("calculator.add", timeout_s=1.0)
            assert result.success is True
            assert result.response.data["result"] == {"value": 10}
            assert described.response.data["tool"] == "calculator.add"
        finally:
            service.stop()

    asyncio.run(run())
