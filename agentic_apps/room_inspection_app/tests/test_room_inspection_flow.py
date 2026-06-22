import asyncio
import os
import sys
from pathlib import Path

RUNTIME_SRC = Path(__file__).resolve().parents[3] / "agentic_runtime_src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from agentic_runtime.app_manager import AppManager
from agentic_runtime.ros_bridge_client.cli_client import Ros2CliBridgeClient
from agentic_runtime.server import RuntimeServer


def _runtime_with_missing_ros2() -> RuntimeServer:
    os.environ["AGENTIC_RUNTIME_CONFIG"] = str(RUNTIME_SRC / "configs" / "runtime.yaml")

    async def missing_ros2(command, timeout_s):
        del command, timeout_s
        raise FileNotFoundError("ros2")

    return RuntimeServer.create(mock=False, bridge_client=Ros2CliBridgeClient(runner=missing_ros2))


def test_room_inspection_app_reports_missing_ros_bridge():
    async def run():
        server = _runtime_with_missing_ros2()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("room_inspection_app", place="厨房")
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"

    asyncio.run(run())
