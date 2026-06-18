from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Ros2BridgeProfile:
    name: str
    bridge_type: str = "ros2"
    source_workspace: str = "/home/ubuntu/agentic_ws/ros2_bridge_src"
    installed_root: str = "/opt/agentic/bridges/ros2"
    workspace_root: str = ""
    packages: list[str] = field(default_factory=list)
    launch: dict[str, Any] = field(default_factory=dict)
    capabilities: list[Any] = field(default_factory=list)
    safety: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
