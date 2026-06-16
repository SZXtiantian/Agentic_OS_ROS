from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .app_index import AppIndex
from .errors import DispatchError


DISPATCHER_DIR = Path(__file__).resolve().parent
BUILTIN_APP_IDS = {"builtin.status", "builtin.stop", "builtin.tasks", "builtin.last_task", "builtin.help", "unsupported"}


class DispatcherValidator:
    def validate(self, plan: dict[str, Any], app_index: AppIndex, flags: Any) -> dict[str, Any]:
        if not isinstance(plan, dict):
            raise DispatchError("DISPATCH_PLAN_INVALID", "route plan must be a JSON object")
        self.validate_schema(plan)
        self.assert_no_direct_robot_references(plan)
        self.validate_route_policy(plan, app_index, flags)
        validated = dict(plan)
        validated["validated"] = True
        return validated

    def validate_schema(self, plan: dict[str, Any]) -> None:
        try:
            Draft202012Validator(_schema()).validate(plan)
        except ValidationError as exc:
            raise DispatchError("DISPATCH_LLM_SCHEMA_INVALID", exc.message) from exc

    def validate_route_policy(self, plan: dict[str, Any], app_index: AppIndex, flags: Any) -> None:
        selected_app_id = str(plan.get("selected_app_id", ""))
        intent = str(plan.get("intent", ""))
        if selected_app_id == "unsupported" or intent == "unsupported":
            raise DispatchError("DISPATCH_UNSAFE_REQUEST_REJECTED", str(plan.get("user_summary") or "unsupported task"))
        if selected_app_id not in BUILTIN_APP_IDS:
            entry = app_index.get(selected_app_id)
            if entry is None:
                raise DispatchError("DISPATCH_APP_NOT_FOUND", f"app not found: {selected_app_id}")
            if not entry.dispatch_enabled:
                raise DispatchError("DISPATCH_APP_DISABLED", f"app is not dispatch-enabled: {selected_app_id}")
            if intent not in entry.intents:
                raise DispatchError("DISPATCH_INTENT_UNSUPPORTED", f"{selected_app_id} does not support {intent}")
            target = str(plan.get("target", "workspace"))
            if target not in (entry.allowed_targets or ["workspace"]):
                raise DispatchError("DISPATCH_TARGET_NOT_ALLOWED", f"target is not allowlisted: {target}")
        elif not _builtin_matches_intent(selected_app_id, intent):
            raise DispatchError("DISPATCH_INTENT_UNSUPPORTED", f"{selected_app_id} does not support {intent}")

        if str(plan.get("target", "")) != "workspace":
            raise DispatchError("DISPATCH_TARGET_NOT_ALLOWED", "only workspace target is allowed")
        expected = self.classify_risk(plan)
        if str(plan.get("risk_class")) != expected:
            raise DispatchError("DISPATCH_RISK_CLASS_INVALID", f"expected {expected}, got {plan.get('risk_class')}")

        if bool(plan.get("requires_robot_motion")) and not bool(getattr(flags, "dry_run", False)):
            motion_allowed = bool(getattr(flags, "allow_arm_motion", False)) or os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION") == "1"
            if not motion_allowed:
                raise DispatchError("DISPATCH_MOTION_DISABLED", "named robot motion requires explicit operator opt-in")
            if bool(plan.get("needs_confirmation")) and not bool(getattr(flags, "assume_yes", False)):
                raise DispatchError("DISPATCH_CONFIRMATION_REQUIRED", "named robot motion requires confirmation")

    def classify_risk(self, plan: dict[str, Any]) -> str:
        selected_app_id = str(plan.get("selected_app_id", ""))
        if selected_app_id == "unsupported" or str(plan.get("intent")) == "unsupported":
            return "unsupported"
        if selected_app_id == "builtin.stop" or str(plan.get("intent")) == "robot_stop":
            return "emergency_control"
        if bool(plan.get("requires_robot_motion")):
            return "named_motion"
        return "read_only"

    def assert_no_direct_robot_references(self, plan: dict[str, Any]) -> None:
        haystack = json.dumps(plan, ensure_ascii=False).lower()
        for pattern in _forbidden_patterns():
            if pattern.lower() in haystack:
                raise DispatchError("DISPATCH_UNSAFE_REQUEST_REJECTED", f"direct robot middleware/control reference is not allowed: {pattern}")


def parse_strict_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        raise DispatchError("DISPATCH_LLM_OUTPUT_INVALID_JSON", "markdown fenced JSON is not accepted")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise DispatchError("DISPATCH_LLM_OUTPUT_INVALID_JSON", "route plan is not valid JSON") from exc
    if not isinstance(data, dict):
        raise DispatchError("DISPATCH_PLAN_INVALID", "route plan must be a JSON object")
    return data


def _schema() -> dict[str, Any]:
    return json.loads((DISPATCHER_DIR / "schemas" / "task_route_plan.schema.json").read_text(encoding="utf-8"))


def _builtin_matches_intent(selected_app_id: str, intent: str) -> bool:
    return {
        "builtin.status": "robot_status",
        "builtin.stop": "robot_stop",
        "builtin.tasks": "tasks",
        "builtin.last_task": "last_task",
        "builtin.help": "help",
        "unsupported": "unsupported",
    }.get(selected_app_id) == intent


def _forbidden_patterns() -> list[str]:
    slash = "/"
    return [
        slash + "cmd_vel",
        slash + "scan",
        slash + "odom",
        slash + "tf",
        slash + "camera",
        slash + "servo",
        slash + "servo_controller",
        slash + "kinematics",
        "camera_pitch_down_15",
        "left_down.d6a",
        "right_down.d6a",
        "joint_trajectory",
        "jointtrajectory",
        "cartesian",
        "freeform_grasp",
        "free grasp",
        "base movement",
        "gazebo",
        "gz",
        "rviz-only",
        "move" + "group",
        "move" + "it",
        "nav" + "2",
        "action" + "client",
        "create_" + "publisher",
        "create_" + "subscription",
    ]
