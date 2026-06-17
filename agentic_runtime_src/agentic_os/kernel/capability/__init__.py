"""AgenticOS capability kernel module."""

from .manager import RobotCapabilityManager
from .registry import CapabilityKind, CapabilityRegistry, CapabilitySpec, Ros2InterfaceSpec

__all__ = [
    "CapabilityKind",
    "CapabilityRegistry",
    "CapabilitySpec",
    "RobotCapabilityManager",
    "Ros2InterfaceSpec",
]
