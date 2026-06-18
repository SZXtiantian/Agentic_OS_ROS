from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4


HIGH_RISK_ACTIONS = {"delete", "overwrite", "rollback", "share", "privilege_change"}
HIGH_RISK_OPERATIONS = {
    "storage.delete",
    "storage.rollback",
    "storage.share",
    "storage.overwrite",
    "storage.overwrite_protected",
    "access.privilege_change",
    "tool.install",
    "tool.execute_admin",
    "bridge.install_profile",
    "bridge.rollback_profile",
    "robot_motion.real_hardware",
}
SHARED_READ_LABELS = {"shared", "app_shared", "operator_shared"}
ROBOT_MOTION_PREFIXES = ("robot.", "arm.", "gripper.", "nav2.", "moveit.", "cmd_vel")


@dataclass(frozen=True)
class AccessSubject:
    agent_name: str
    app_id: str = ""
    user_id: str = ""
    session_id: str = ""
    groups: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessResource:
    resource_type: str
    resource_id: str
    owner_agent: str = ""
    owner_user: str = ""
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessRequest:
    subject: AccessSubject
    action: str
    resource: AccessResource
    irreversible: bool = False
    reason: str = ""


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    error_code: str = ""
    reason: str = ""
    requires_intervention: bool = False
    intervention_id: str = ""
    decision_id: str = field(default_factory=lambda: f"acd_{uuid4().hex[:16]}")
    metadata: dict[str, Any] = field(default_factory=dict)


class AccessPolicy(Protocol):
    def evaluate(self, request: AccessRequest) -> AccessDecision:
        ...


def is_owner(subject: AccessSubject, resource: AccessResource) -> bool:
    return bool(
        (resource.owner_agent and resource.owner_agent == subject.agent_name)
        or (resource.owner_user and subject.user_id and resource.owner_user == subject.user_id)
    )


def is_shared_read(resource: AccessResource) -> bool:
    return bool(set(resource.labels) & SHARED_READ_LABELS)


def is_robot_motion_resource(resource: AccessResource) -> bool:
    resource_id = resource.resource_id.lower()
    resource_type = resource.resource_type.lower()
    return resource_type == "robot_motion" or resource_id.startswith(ROBOT_MOTION_PREFIXES)


class DefaultAccessPolicy:
    """Small static ACL for kernel resources and robot safety gates."""

    def evaluate(self, request: AccessRequest) -> AccessDecision:
        action = request.action.lower()
        resource_type = request.resource.resource_type.lower()
        groups = set(request.subject.groups)

        if resource_type == "audit" and action == "delete":
            return AccessDecision(
                allowed=False,
                error_code="ACCESS_AUDIT_DELETE_FORBIDDEN",
                reason="audit log deletion is permanently forbidden",
            )

        if action == "execute" and is_robot_motion_resource(request.resource):
            if "robot_operator" not in groups and not self._has_robot_permission(request.subject):
                return AccessDecision(
                    allowed=False,
                    error_code="ACCESS_ROBOT_OPERATOR_REQUIRED",
                    reason="robot motion execution requires robot_operator group or explicit robot permission",
                )
            return AccessDecision(allowed=True, reason="robot motion access allowed")

        if action == "execute" and resource_type == "robot_sensor":
            if not self._has_robot_sensor_permission(request.subject):
                return AccessDecision(
                    allowed=False,
                    error_code="ACCESS_ROBOT_SENSOR_PERMISSION_REQUIRED",
                    reason="robot sensor execution requires explicit perception or robot state permission",
                )
            return AccessDecision(allowed=True, reason="robot sensor access allowed")

        if "admin" in groups:
            return AccessDecision(allowed=True, reason="admin access allowed")

        if resource_type in {"memory", "storage"}:
            if is_owner(request.subject, request.resource):
                return AccessDecision(allowed=True, reason="owner access allowed")
            if action == "read" and is_shared_read(request.resource):
                return AccessDecision(allowed=True, reason="shared read access allowed")
            if action == "write" and is_shared_read(request.resource):
                return AccessDecision(
                    allowed=False,
                    error_code="ACCESS_SHARED_WRITE_DENIED",
                    reason="shared resources are read-only for non-owners",
                )
            return AccessDecision(
                allowed=False,
                error_code="ACCESS_DENIED",
                reason="private resource access denied",
            )

        if action == "read" and is_shared_read(request.resource):
            return AccessDecision(allowed=True, reason="shared read access allowed")

        if action == "execute" and self._has_execute_permission(request.subject, request.resource):
            return AccessDecision(allowed=True, reason="execute permission allowed")

        return AccessDecision(
            allowed=False,
            error_code="ACCESS_DENIED",
            reason="no matching access policy",
        )

    def _has_robot_permission(self, subject: AccessSubject) -> bool:
        permissions = set(subject.permissions)
        return bool(
            permissions
            & {
                "robot.move",
                "robot.stop",
                "robot.motion.execute",
                "robot.operator",
                "arm.move.named",
                "gripper.control",
                "skill.execute.robot",
            }
        )

    def _has_robot_sensor_permission(self, subject: AccessSubject) -> bool:
        permissions = set(subject.permissions)
        return bool(
            permissions
            & {
                "perception.inspect",
                "perception.observe",
                "perception.capture",
                "robot.state.read",
                "robot.sensor.read",
            }
        )

    def _has_execute_permission(self, subject: AccessSubject, resource: AccessResource) -> bool:
        permissions = set(subject.permissions)
        resource_type = resource.resource_type.lower()
        resource_id = resource.resource_id
        return bool(
            {
                f"{resource_type}.execute",
                f"{resource_type}.execute.{resource_id}",
                f"{resource_id}.execute",
                resource_id,
            }
            & permissions
        )


def operation_key(request: AccessRequest) -> str:
    resource_type = request.resource.resource_type.lower()
    action = request.action.lower()
    resource_id = request.resource.resource_id.lower()
    if resource_type == "robot_motion" and resource_id == "real_hardware":
        return "robot_motion.real_hardware"
    return f"{resource_type}.{action}"


def requires_intervention(request: AccessRequest) -> bool:
    if request.irreversible:
        return True
    action = request.action.lower()
    resource_type = request.resource.resource_type.lower()
    resource_id = request.resource.resource_id.lower()
    candidates = {
        action,
        f"{resource_type}.{action}",
        f"{resource_type}.{resource_id}",
        operation_key(request),
    }
    return bool((candidates & HIGH_RISK_OPERATIONS) or action in HIGH_RISK_ACTIONS)
