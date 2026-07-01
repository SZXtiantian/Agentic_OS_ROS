from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any

import yaml


AGENTIC_SKILL_BLOCK_RE = re.compile(
    r"^```json[ \t]+agentic-skill[^\n]*\n(?P<body>.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


class CapabilityKind:
    RUNTIME_INTERNAL = "runtime_internal"
    SIMULATED_DISABLED = "simulated_disabled"
    ROS2_TOPIC = "ros2_topic"
    ROS2_SERVICE = "ros2_service"
    ROS2_ACTION = "ros2_action"
    NAV2_ACTION = "nav2_action"
    MOVEIT_ACTION = "moveit_action"
    PERCEPTION = "perception"
    HARDWARE_DRIVER = "hardware_driver"


@dataclass(frozen=True)
class Ros2InterfaceSpec:
    kind: str
    name: str
    type: str = ""
    bridge: str = ""
    backend_name: str = ""
    backend_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilitySpec:
    name: str
    kind: str
    description: str = ""
    permissions: list[str] = field(default_factory=list)
    resource_locks: list[str] = field(default_factory=list)
    safety_constraints: dict[str, Any] = field(default_factory=dict)
    observability: dict[str, Any] = field(default_factory=dict)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    ros2: Ros2InterfaceSpec | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_skill_manifest(cls, data: dict[str, Any]) -> "CapabilitySpec":
        backend = dict(data.get("backend") or data.get("implementation") or {})
        kind = _kind_from_backend(data.get("name", ""), backend)
        ros2 = _ros2_from_backend(kind, backend)
        return cls(
            name=str(data["name"]),
            kind=kind,
            description=str(data.get("description") or ""),
            permissions=list(data.get("permission_requirements") or []),
            resource_locks=list((data.get("resource_requirements") or {}).get("locks") or []),
            safety_constraints=dict(data.get("safety_constraints") or {}),
            observability=dict(data.get("observability") or {}),
            input_schema=dict(data.get("input_schema") or {}),
            output_schema=dict(data.get("output_schema") or {}),
            ros2=ros2,
            metadata={"backend": backend, "version": str(data.get("version") or "")},
        )

    def validate_os_contract(self) -> list[str]:
        failures: list[str] = []
        if self.name.startswith("robot.") and "robot.stop" != self.name:
            if not self.permissions:
                failures.append(f"{self.name}: robot capability requires permission requirements")
            if not self.safety_constraints:
                failures.append(f"{self.name}: robot capability requires safety constraints")
        if self.name in {"robot.navigate_to", "robot.inspect_area"} and not self.resource_locks:
            failures.append(f"{self.name}: dangerous capability requires resource locks")
        if self.kind in {CapabilityKind.ROS2_SERVICE, CapabilityKind.ROS2_ACTION, CapabilityKind.NAV2_ACTION, CapabilityKind.MOVEIT_ACTION}:
            if self.ros2 is None or not self.ros2.name:
                failures.append(f"{self.name}: ROS2 capability requires an interface name")
        if self.kind == CapabilityKind.SIMULATED_DISABLED:
            failures.append(f"{self.name}: simulated capability backend is disabled")
        if self.kind == CapabilityKind.NAV2_ACTION and not (self.ros2 and self.ros2.backend_name):
            failures.append(f"{self.name}: Nav2 capability requires backend action mapping")
        if self.name.startswith("robot.") and not self.observability.get("audit", False):
            failures.append(f"{self.name}: robot capability requires audit observability")
        return failures

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ros2"] = self.ros2.to_dict() if self.ros2 else None
        return data


class CapabilityRegistry:
    """Kernel registry for task-level robot capabilities.

    The registry is the AgenticOS equivalent of an OS device/capability table:
    it normalizes app-facing APIs into runtime-internal, ROS2 service/action,
    Nav2, MoveIt, perception, or hardware-driver resources.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilitySpec] = {}

    def register(self, spec: CapabilitySpec) -> None:
        failures = spec.validate_os_contract()
        if failures:
            raise ValueError("; ".join(failures))
        self._capabilities[spec.name] = spec

    def register_skill_manifest(self, data: dict[str, Any]) -> CapabilitySpec:
        spec = CapabilitySpec.from_skill_manifest(data)
        self.register(spec)
        return spec

    def load_skill_manifests(self, root: str | Path) -> "CapabilityRegistry":
        skill_root = Path(root)
        for path in sorted(skill_root.glob("*/SKILL.md")):
            data = _load_agentic_skill_markdown(path)
            self.register_skill_manifest(data)
        for path in sorted(skill_root.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            self.register_skill_manifest(data)
        return self

    def get(self, name: str) -> CapabilitySpec | None:
        return self._capabilities.get(name)

    def list(self) -> list[CapabilitySpec]:
        return [self._capabilities[name] for name in sorted(self._capabilities)]

    def by_kind(self, kind: str) -> list[CapabilitySpec]:
        return [spec for spec in self.list() if spec.kind == kind]

    def validate(self) -> list[str]:
        failures: list[str] = []
        for spec in self.list():
            failures.extend(spec.validate_os_contract())
        return failures

    def to_dict(self) -> dict[str, Any]:
        return {name: spec.to_dict() for name, spec in sorted(self._capabilities.items())}


def _kind_from_backend(name: str, backend: dict[str, Any]) -> str:
    backend_type = str(backend.get("type") or "")
    if backend_type == "runtime_internal":
        return CapabilityKind.RUNTIME_INTERNAL
    if backend.get("ros2_backend_action_type", "").startswith("moveit_msgs/"):
        return CapabilityKind.MOVEIT_ACTION
    if backend.get("ros2_backend_action_type", "").startswith("nav2_msgs/") or backend.get("ros2_backend_action") == "/navigate_to_pose":
        return CapabilityKind.NAV2_ACTION
    if backend.get("action"):
        return CapabilityKind.ROS2_ACTION
    if backend.get("service"):
        if name.startswith("robot.inspect") or name.startswith("perception."):
            return CapabilityKind.PERCEPTION
        return CapabilityKind.ROS2_SERVICE
    if backend.get("topic"):
        return CapabilityKind.ROS2_TOPIC
    if backend_type in {"mock", "fake", "stub", "dummy"}:
        return CapabilityKind.SIMULATED_DISABLED
    return backend_type or CapabilityKind.RUNTIME_INTERNAL


def _load_agentic_skill_markdown(path: Path) -> dict[str, Any]:
    markdown = path.read_text(encoding="utf-8")
    match = AGENTIC_SKILL_BLOCK_RE.search(markdown)
    if match is None:
        raise ValueError(f"CAPABILITY_CONTRACT_INVALID: {path}: missing json agentic-skill metadata block")
    data = json.loads(match.group("body"))
    if not isinstance(data, dict):
        raise ValueError(f"CAPABILITY_CONTRACT_INVALID: {path}: metadata must be an object")
    data = dict(data)
    data.setdefault("backend", dict(data.get("implementation") or {}))
    return data


def _ros2_from_backend(kind: str, backend: dict[str, Any]) -> Ros2InterfaceSpec | None:
    if kind not in {
        CapabilityKind.ROS2_TOPIC,
        CapabilityKind.ROS2_SERVICE,
        CapabilityKind.ROS2_ACTION,
        CapabilityKind.NAV2_ACTION,
        CapabilityKind.MOVEIT_ACTION,
        CapabilityKind.PERCEPTION,
    }:
        return None
    if backend.get("action"):
        return Ros2InterfaceSpec(
            kind="action",
            name=str(backend.get("action") or ""),
            type=str(backend.get("action_type") or ""),
            bridge=str(backend.get("bridge") or ""),
            backend_name=str(backend.get("ros2_backend_action") or ""),
            backend_type=str(backend.get("ros2_backend_action_type") or ""),
        )
    if backend.get("service"):
        return Ros2InterfaceSpec(
            kind="service",
            name=str(backend.get("service") or ""),
            type=str(backend.get("service_type") or ""),
            bridge=str(backend.get("bridge") or ""),
        )
    if backend.get("topic"):
        return Ros2InterfaceSpec(
            kind="topic",
            name=str(backend.get("topic") or ""),
            type=str(backend.get("topic_type") or ""),
            bridge=str(backend.get("bridge") or ""),
        )
    return None
