from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from types import SimpleNamespace

from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
from agentic_os.kernel.hooks import InMemoryKernelEventSink
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
    missing_status = manager.address_request(
        SimpleNamespace(agent_name="agent_a", operation_type="tool_status", params={"call_id": "missing"})
    )
    cancel = manager.address_request(SimpleNamespace(agent_name="agent_a", operation_type="tool_cancel", params={"call_id": "x"}))

    assert described["success"] is True
    assert described["builtin"] is True
    assert status["status"]["registered"]
    assert missing_status["success"] is False
    assert missing_status["error_code"] == "SYSCALL_NOT_FOUND"
    assert cancel["success"] is False
    assert cancel["error_code"] == "SYSCALL_NOT_FOUND"


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


def test_tool_cancel_active_call_is_cooperative_and_audited(tmp_path):
    sink = InMemoryKernelEventSink()
    manager = ToolManager(tool_root=tmp_path / "tools", event_sink=sink)
    started = threading.Event()

    def slow(args):
        cancel_event = args["_cancel_event"]
        started.set()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if cancel_event.is_set():
                return {"stopped": True}
            time.sleep(0.01)
        return {"stopped": False}

    manager.register("slow.tool", slow)
    result: dict[str, object] = {}

    def run_tool():
        response = manager.address_request(
            SimpleNamespace(
                agent_name="agent_a",
                operation_type="tool_call",
                params={"name": "slow.tool", "args": {}, "call_id": "tool_call_1"},
            )
        )
        result.update(response.as_mapping())

    thread = threading.Thread(target=run_tool)
    thread.start()
    assert started.wait(timeout=1.0)

    status = manager.status()
    active_status = manager.address_request(
        SimpleNamespace(agent_name="agent_a", operation_type="tool_status", params={"call_id": "tool_call_1"})
    )
    cancel = manager.address_request(
        SimpleNamespace(agent_name="agent_a", operation_type="tool_cancel", params={"call_id": "tool_call_1"})
    )
    thread.join(timeout=1.0)

    assert status["active_calls"] == [{"call_id": "tool_call_1", "agent_name": "agent_a", "tool": "slow.tool"}]
    assert active_status["success"] is True
    assert active_status["active_call"] == {"call_id": "tool_call_1", "agent_name": "agent_a", "tool": "slow.tool"}
    assert cancel["success"] is True
    assert result["success"] is False
    assert result["error_code"] == "TOOL_CANCELLED"
    assert manager.status()["active_calls"] == []
    assert any(
        event["event_type"] == "tool.cancel_requested" and event["metadata"]["call_id"] == "tool_call_1"
        for event in sink.recent(limit=20)
    )
    assert any(
        event["event_type"] == "tool.status" and event["metadata"]["call_id"] == "tool_call_1"
        for event in sink.recent(limit=20)
    )


def test_tool_load_unload_register_builtin_without_permission_are_denied(tmp_path):
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
        status = service.status()
    finally:
        service.stop()

    assert loaded.success is False
    assert loaded.error_code == "ACCESS_DENIED"
    assert unloaded.success is False
    assert unloaded.error_code == "ACCESS_DENIED"
    assert registered.success is False
    assert registered.error_code == "ACCESS_DENIED"
    audit_events = [event for event in status["events"]["recent"] if event["event_type"] == "tool.audit"]
    assert [event["metadata"]["action"] for event in audit_events] == [
        "load_manifest",
        "unload",
        "register_builtin",
    ]
    assert all(event["metadata"]["error_code"] == "ACCESS_DENIED" for event in audit_events)


def test_tool_load_unload_register_builtin_with_permission_require_intervention(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    manifest = service.tool.tool_root / "sample.yaml"
    manifest.write_text("name: sample.tool\nentrypoint: sample:run\n", encoding="utf-8")
    service.start()
    try:
        loaded = service.execute_request(
            "agent_a",
            ToolQuery(
                operation_type="tool_load_manifest",
                params={"path": str(manifest), "permissions": ["tool.install"]},
            ),
            timeout_s=1.0,
        )
        unloaded = service.execute_request(
            "agent_a",
            ToolQuery(
                operation_type="tool_unload",
                params={"name": "calculator.add", "permissions": ["tool.uninstall"]},
            ),
            timeout_s=1.0,
        )
        registered = service.execute_request(
            "agent_a",
            ToolQuery(
                operation_type="tool_register_builtin",
                params={"name": "calculator.add", "permissions": ["tool.register_builtin"]},
            ),
            timeout_s=1.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert loaded.success is False
    assert loaded.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert unloaded.success is False
    assert unloaded.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert registered.success is False
    assert registered.error_code == "ACCESS_INTERVENTION_REQUIRED"
    audit_events = [event for event in status["events"]["recent"] if event["event_type"] == "tool.audit"]
    assert [event["metadata"]["action"] for event in audit_events] == [
        "load_manifest",
        "unload",
        "register_builtin",
    ]
    assert all(event["metadata"]["error_code"] == "ACCESS_INTERVENTION_REQUIRED" for event in audit_events)


def test_tool_management_requires_access_manager_before_registry_change(tmp_path):
    tool_root = tmp_path / "tools"
    tool_root.mkdir()
    (tool_root / "sample.py").write_text("def run(args):\n    return {'ok': True}\n", encoding="utf-8")
    manifest = tool_root / "sample.tool.yaml"
    manifest.write_text("name: sample.tool\nentrypoint: sample:run\n", encoding="utf-8")
    sink = InMemoryKernelEventSink()
    manager = ToolManager(tool_root=tool_root, event_sink=sink)

    loaded = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="tool_load_manifest",
            params={"path": str(manifest), "permissions": ["tool.install"]},
        )
    )
    unloaded = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="tool_unload",
            params={"name": "calculator.add", "permissions": ["tool.uninstall"]},
        )
    )
    registered = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="tool_register_builtin",
            params={"name": "calculator.add", "permissions": ["tool.register_builtin"]},
        )
    )

    assert loaded.success is False
    assert loaded.error_code == "ACCESS_MANAGER_UNAVAILABLE"
    assert unloaded.success is False
    assert unloaded.error_code == "ACCESS_MANAGER_UNAVAILABLE"
    assert registered.success is False
    assert registered.error_code == "ACCESS_MANAGER_UNAVAILABLE"
    assert manager.describe("sample.tool")["success"] is False
    assert manager.describe("calculator.add")["success"] is True
    events = [event for event in sink.recent(limit=10) if event["event_type"] == "tool.audit"]
    assert [event["metadata"]["action"] for event in events] == ["load_manifest", "unload", "register_builtin"]
    assert all(event["metadata"]["error_code"] == "ACCESS_MANAGER_UNAVAILABLE" for event in events)


def test_dangerous_tool_operations_emit_audit_events(tmp_path):
    tool_root = tmp_path / "tools"
    tool_root.mkdir()
    (tool_root / "sample.py").write_text("def run(args):\n    return {'ok': True}\n", encoding="utf-8")
    manifest = tool_root / "sample.tool.yaml"
    manifest.write_text(
        """
name: sample.tool
entrypoint: sample:run
sandbox:
  mode: in_process
""",
        encoding="utf-8",
    )
    sink = InMemoryKernelEventSink()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    manager = ToolManager(tool_root=tool_root, access_manager=access, event_sink=sink)

    loaded = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="tool_load_manifest",
            params={"path": str(manifest), "permissions": ["tool.install"]},
        )
    )
    unloaded = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="tool_unload",
            params={"name": "sample.tool", "permissions": ["tool.uninstall"]},
        )
    )
    registered = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="tool_register_builtin",
            params={"name": "calculator.add", "permissions": ["tool.register_builtin"]},
        )
    )

    assert loaded["success"] is True
    assert unloaded["success"] is True
    assert registered["success"] is True
    events = [event for event in sink.recent(limit=20) if event["event_type"] == "tool.audit"]
    assert [event["metadata"]["action"] for event in events] == ["load_manifest", "unload", "register_builtin"]
    assert all(event["metadata"]["success"] is True for event in events)
    assert all(event["metadata"]["irreversible"] is True for event in events)


def test_kernel_tool_sdk_permissions_from_manifest(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    manifest = service.tool.tool_root / "sample.yaml"
    manifest.write_text("name: sample.tool\nentrypoint: sample:run\n", encoding="utf-8")

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
            manager_app = AppManifest("tool_manager_app", "0", "", "main:run", ["tool.install"], [])
            manager_ctx = AgentContext(Executor(), manager_app, "sess_tool_manage")
            manager_result = await manager_ctx.kernel.tool.load_manifest(str(manifest), timeout_s=1.0)
            assert result.success is True
            assert result.response.data["result"] == {"value": 10}
            assert described.response.data["tool"] == "calculator.add"
            assert manager_result.success is False
            assert manager_result.error_code == "ACCESS_INTERVENTION_REQUIRED"
        finally:
            service.stop()

    asyncio.run(run())
