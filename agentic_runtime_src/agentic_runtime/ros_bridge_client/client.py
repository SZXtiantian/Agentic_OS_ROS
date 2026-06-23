from __future__ import annotations

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.provider_contracts import ros_bridge_contract

from .cli_client import Ros2CliBridgeClient


class RosBridgeModeUnsupportedError(RuntimeError):
    error_code = "ROS_BRIDGE_MODE_UNSUPPORTED"

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.status = ros_bridge_contract(mode)
        super().__init__(f"{self.error_code}: unsupported ROS bridge mode: {mode}")


def create_ros_bridge_client(config: RuntimeConfig):
    if config.ros_bridge_mode == "cli":
        return Ros2CliBridgeClient()
    raise RosBridgeModeUnsupportedError(config.ros_bridge_mode)
