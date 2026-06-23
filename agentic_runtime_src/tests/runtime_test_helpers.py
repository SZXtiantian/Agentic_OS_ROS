from __future__ import annotations

import os
from pathlib import Path

from agentic_runtime.ros_bridge_client.cli_client import Ros2CliBridgeClient
from agentic_runtime.server import RuntimeServer


def create_test_runtime_server() -> RuntimeServer:
    os.environ["AGENTIC_RUNTIME_CONFIG"] = str(Path(__file__).resolve().parents[1] / "configs" / "runtime.yaml")
    bridge_calls = []

    async def missing_ros2(command, timeout_s):
        bridge_calls.append({"command": command, "timeout_s": timeout_s})
        raise FileNotFoundError("ros2")

    server = RuntimeServer.create(bridge_client=Ros2CliBridgeClient(runner=missing_ros2))
    server.test_bridge_calls = bridge_calls
    return server
