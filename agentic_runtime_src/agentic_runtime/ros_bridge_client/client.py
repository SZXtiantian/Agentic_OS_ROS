from __future__ import annotations

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.simulation import SIMULATED_BACKEND_DISABLED

from .cli_client import Ros2CliBridgeClient


def create_ros_bridge_client(config: RuntimeConfig, mock: bool = False):
    if mock or config.ros_bridge_mode == "mock":
        raise RuntimeError(SIMULATED_BACKEND_DISABLED)
    if config.ros_bridge_mode == "cli":
        return Ros2CliBridgeClient()
    raise RuntimeError(f"unsupported ROS bridge mode: {config.ros_bridge_mode}")
