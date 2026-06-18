from __future__ import annotations

import threading
import time

import pytest

from agentic_os.kernel.system_call import KernelSyscall
from agentic_os.kernel.tool import MCPToolServer, ToolManager, ToolSandboxPolicy


def test_dynamic_tool_loads_from_tool_root(tmp_path):
    tool_root = tmp_path / "tools"
    tool_root.mkdir()
    (tool_root / "calculator.py").write_text(
        "def add(args):\n    return {'sum': args['a'] + args['b']}\n",
        encoding="utf-8",
    )
    manifest = tool_root / "calculator.add.yaml"
    manifest.write_text(
        """
name: calculator.add
entrypoint: calculator:add
description: Add numbers
permissions:
  - tool.execute.calculator
conflicts:
  - calculator.add
sandbox:
  mode: in_process
  network: false
  filesystem: false
mcp:
  enabled: false
""",
        encoding="utf-8",
    )
    manager = ToolManager(tool_root=tool_root)

    loaded = manager.load_manifest(manifest)
    result = manager.address_request(
        KernelSyscall.create("agent_a", "tool", "call_tool", {"name": loaded.name, "args": {"a": 1, "b": 2}})
    )

    assert result["success"] is True
    assert result["result"] == {"sum": 3}
    assert loaded.version == "0"
    assert loaded.mcp == {"enabled": False}
    assert manager.status()["recent_events"][-1]["event_type"] == "tool.done"


def test_tool_conflict_map_blocks_same_tool_concurrent_execution():
    manager = ToolManager()
    started = threading.Event()

    def slow(args):
        started.set()
        time.sleep(0.05)
        return {"ok": True}

    manager.register("slow.tool", slow)
    first_result = {}

    def run_first():
        first_result.update(
            manager.address_request(
                KernelSyscall.create("agent_a", "tool", "slow.tool", {"name": "slow.tool", "args": {}})
            )
        )

    thread = threading.Thread(target=run_first)
    thread.start()
    assert started.wait(timeout=1.0)

    second = manager.address_request(
        KernelSyscall.create("agent_b", "tool", "slow.tool", {"name": "slow.tool", "args": {}})
    )
    thread.join(timeout=1.0)

    assert second["success"] is False
    assert second["error_code"] == "TOOL_BUSY"
    assert first_result["success"] is True


def test_robot_tool_prefix_forbidden():
    manager = ToolManager()

    result = manager.address_request(
        KernelSyscall.create("agent_a", "tool", "robot.navigate_to", {"name": "robot.navigate_to"})
    )

    assert result["success"] is False
    assert result["error_code"] == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"


def test_cmd_vel_path_prefix_forbidden():
    manager = ToolManager()

    result = manager.address_request(
        KernelSyscall.create("agent_a", "tool", "/cmd_vel", {"name": "/cmd_vel"})
    )

    assert result["success"] is False
    assert result["error_code"] == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"


def test_tool_outside_tool_root_rejected(tmp_path):
    tool_root = tmp_path / "tools"
    outside = tmp_path / "outside"
    tool_root.mkdir()
    outside.mkdir()
    manifest = outside / "tool.yaml"
    manifest.write_text("name: outside.tool\nentrypoint: outside:run\n", encoding="utf-8")
    manager = ToolManager(tool_root=tool_root)

    with pytest.raises(ValueError, match="outside tool root"):
        manager.load_manifest(manifest)


def test_mcp_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENTIC_ENABLE_MCP_TOOLS", raising=False)

    server = MCPToolServer()

    assert server.status() == {"enabled": False, "implemented": True, "running": False, "tool_count": 0}
    assert server.start()["error_code"] == "TOOL_MCP_DISABLED"
    assert server.list_tools()["error_code"] == "TOOL_MCP_DISABLED"


def test_mcp_enabled_lifecycle_and_call():
    server = MCPToolServer(enabled=True)
    server.register_tool("echo", lambda args: {"message": args["message"]})

    assert server.list_tools()["error_code"] == "TOOL_MCP_NOT_RUNNING"
    assert server.start() == {"success": True, "status": "running"}
    assert server.list_tools() == {"success": True, "tools": ["echo"]}
    assert server.call_tool("echo", {"message": "hi"})["result"] == {"message": "hi"}
    assert server.stop() == {"success": True, "status": "stopped"}


def test_sandbox_rejects_network_and_disabled_modes(tmp_path):
    tool_root = tmp_path / "tools"
    tool_root.mkdir()
    manager = ToolManager(tool_root=tool_root)

    assert manager.sandbox_policy.validate({"mode": "subprocess"})["error_code"] == "TOOL_SANDBOX_MODE_DISABLED"
    assert manager.sandbox_policy.validate({"network": True})["error_code"] == "TOOL_SANDBOX_NETWORK_DISABLED"


def test_manifest_network_sandbox_rejected(tmp_path):
    tool_root = tmp_path / "tools"
    tool_root.mkdir()
    (tool_root / "calculator.py").write_text("def add(args):\n    return {'ok': True}\n", encoding="utf-8")
    manifest = tool_root / "calculator.add.yaml"
    manifest.write_text(
        """
name: calculator.add
entrypoint: calculator:add
sandbox:
  mode: in_process
  network: true
""",
        encoding="utf-8",
    )
    manager = ToolManager(tool_root=tool_root)

    with pytest.raises(ValueError, match="TOOL_SANDBOX_NETWORK_DISABLED"):
        manager.load_manifest(manifest)


def test_sandbox_policy_allows_workspace_write_under_tool_root(tmp_path):
    policy = ToolSandboxPolicy(workspace_root=tmp_path)

    result = policy.validate({"filesystem": "workspace_write", "workspace": "workspace"})

    assert result["success"] is True
    assert result["sandbox"]["filesystem"] == "workspace_write"
