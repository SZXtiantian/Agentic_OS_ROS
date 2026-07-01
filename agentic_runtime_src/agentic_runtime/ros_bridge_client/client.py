from __future__ import annotations

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.provider_contracts import ros_bridge_contract

from agentic_runtime.skill_runtime.ros2_client import Ros2SkillRuntimeClient


class RosBridgeModeUnsupportedError(RuntimeError):
    error_code = "ROS_BRIDGE_MODE_UNSUPPORTED"

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.status = ros_bridge_contract(mode)
        super().__init__(f"{self.error_code}: unsupported ROS bridge mode: {mode}")


def create_ros_bridge_client(config: RuntimeConfig):
    transport = _configured_transport(config)
    if transport == "cli":
        return Ros2SkillRuntimeClient()
    raise RosBridgeModeUnsupportedError(transport)


def _configured_transport(config: RuntimeConfig) -> str:
    provider_transport = str(getattr(config, "skill_provider_transport", "cli") or "cli")
    legacy_transport = str(getattr(config, "ros_bridge_mode", provider_transport) or provider_transport)
    if provider_transport != "cli":
        return provider_transport
    return legacy_transport
