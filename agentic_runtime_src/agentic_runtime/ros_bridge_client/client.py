from __future__ import annotations

from agentic_runtime.config import RuntimeConfig

from .cli_client import Ros2CliBridgeClient


def create_ros_bridge_client(config: RuntimeConfig, mock: bool = False):
    if mock or config.ros_bridge_mode == "mock":
        from .mock_client import MockRosBridgeClient

        return MockRosBridgeClient(config.repo_root)
    if config.ros_bridge_mode == "cli":
        return Ros2CliBridgeClient()
    raise RuntimeError(f"unsupported ROS bridge mode: {config.ros_bridge_mode}")
