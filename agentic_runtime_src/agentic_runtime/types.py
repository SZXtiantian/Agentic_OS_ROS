from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class SkillResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    reason: str = ""
    recoverable: bool = True
    suggested_recovery: list[str] = field(default_factory=list)
    audit_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillCall:
    skill_name: str
    args: dict[str, Any]
    app_id: str
    session_id: str
    call_id: str = field(default_factory=lambda: new_id("call"))


@dataclass
class AppManifest:
    name: str
    version: str
    description: str
    entrypoint: str
    permissions: list[str]
    required_capabilities: list[str]
    safety_policy: dict[str, Any] = field(default_factory=dict)
    runtime_limits: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppManifest":
        return cls(
            name=str(data["name"]),
            version=str(data["version"]),
            description=str(data.get("description", "")),
            entrypoint=str(data["entrypoint"]),
            permissions=list(data.get("permissions", [])),
            required_capabilities=list(data.get("required_capabilities", [])),
            safety_policy=dict(data.get("safety_policy", {})),
            runtime_limits=dict(data.get("runtime_limits", {})),
        )


@dataclass
class SkillManifest:
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission_requirements: list[str]
    resource_requirements: dict[str, Any]
    safety_constraints: dict[str, Any]
    timeout_s: int
    retry_policy: dict[str, Any]
    backend: dict[str, Any]
    observability: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifest":
        return cls(
            name=str(data["name"]),
            version=str(data["version"]),
            description=str(data.get("description", "")),
            input_schema=dict(data["input_schema"]),
            output_schema=dict(data["output_schema"]),
            permission_requirements=list(data["permission_requirements"]),
            resource_requirements=dict(data.get("resource_requirements", {"locks": []})),
            safety_constraints=dict(data.get("safety_constraints", {})),
            timeout_s=int(data.get("timeout_s", 60)),
            retry_policy=dict(data.get("retry_policy", {"max_attempts": 0, "retry_on": []})),
            backend=dict(data.get("backend", {"type": "unconfigured"})),
            observability=dict(data.get("observability", {"audit": True})),
        )


@dataclass
class PlaceRef:
    id: str
    name: str
    frame_id: str
    pose: dict[str, float]
    allowed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RobotState:
    robot_id: str
    mode: str
    battery_state: str
    battery_percent: float
    is_localized: bool
    is_moving: bool
    estop_pressed: bool
    current_place: str = ""
    pose: dict[str, float] = field(default_factory=dict)
    active_task_id: str = ""
    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InspectionResult:
    success: bool
    summary: str
    objects: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    evidence_path: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ObservationResult:
    success: bool
    summary: str
    objects: list[str] = field(default_factory=list)
    evidence_path: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PhotoCaptureResult:
    success: bool
    image_path: str = ""
    metadata_path: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    reason: str = ""
    audit_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArmState:
    readiness: str
    active_action: str
    is_moving: bool
    gripper_ready: bool
    stop_available: bool
    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HumanAnswer:
    answered: bool
    answer: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
