from __future__ import annotations

import threading
import time

import pytest

from agentic_os.kernel.system_call import KernelSyscall
from agentic_os.kernel.tool import MCPToolServer, ToolManager


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
  network: false
  filesystem: false
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

    assert MCPToolServer().status() == {"enabled": False, "implemented": False}
