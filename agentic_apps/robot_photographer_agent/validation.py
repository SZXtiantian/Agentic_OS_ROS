from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


APP_DIR = Path(__file__).resolve().parent


class PhotoPlanValidationError(ValueError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def validate_plan(
    plan: dict[str, Any],
    *,
    allow_arm_motion: bool = False,
    assume_yes: bool = False,
    schema_path: str | Path | None = None,
    policy_path: str | Path | None = None,
) -> dict[str, Any]:
    schema = _load_json(Path(schema_path) if schema_path else APP_DIR / "schemas" / "photo_plan.schema.json")
    policy = _load_yaml(Path(policy_path) if policy_path else APP_DIR / "policies" / "robot_photographer.policy.yaml")
    try:
        Draft202012Validator(schema).validate(plan)
    except ValidationError as exc:
        raise PhotoPlanValidationError("PHOTO_PLAN_INVALID", exc.message) from exc

    if plan["intent"] == "unsupported":
        raise PhotoPlanValidationError("PHOTO_INTENT_UNSUPPORTED", plan.get("user_summary", "unsupported task"))

    _validate_target(plan, policy)
    _validate_steps(plan, policy)
    expected_risk = _classify_risk(plan)
    if plan["risk_class"] != expected_risk:
        raise PhotoPlanValidationError("PHOTO_RISK_CLASS_INVALID", f"expected {expected_risk}, got {plan['risk_class']}")

    motion_allowed = allow_arm_motion or os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION") == "1"
    if plan.get("requires_motion") and not motion_allowed:
        raise PhotoPlanValidationError("ARM_MOTION_DISABLED", "named arm motion requires explicit operator opt-in")
    if plan.get("requires_motion") and plan.get("needs_confirmation") and not assume_yes:
        raise PhotoPlanValidationError("ARM_CONFIRMATION_REQUIRED", "named arm motion requires confirmation")

    validated = dict(plan)
    validated["validated"] = True
    return validated


def _validate_target(plan: dict[str, Any], policy: dict[str, Any]) -> None:
    allowed = set(policy.get("targets", {}).get("allowed", ["workspace"]))
    target = str(plan.get("target", "workspace"))
    if target not in allowed:
        raise PhotoPlanValidationError("TARGET_NOT_ALLOWED", f"target is not allowlisted: {target}")


def _validate_steps(plan: dict[str, Any], policy: dict[str, Any]) -> None:
    allowed_actions = set(policy.get("motion", {}).get("allowed_named_actions", []))
    allowed_targets = set(policy.get("targets", {}).get("allowed", ["workspace"]))
    max_arm_timeout = int(policy.get("motion", {}).get("arm_action_timeout_s_max", 8))
    max_burst_count = int(policy.get("burst", {}).get("count_max", 5))
    max_interval = float(policy.get("burst", {}).get("interval_s_max", 5))
    max_capture_timeout = int(policy.get("capture", {}).get("timeout_s_max", 5))
    multi_angle = dict(policy.get("multi_angle") or {})
    max_pose_count = int(multi_angle.get("max_pose_count", 5))
    min_difference_score = float(multi_angle.get("min_image_difference_score", 0.08))
    capture_count = 0
    camera_pose_count = 0
    has_verification = False

    for step in plan.get("steps", []):
        step_type = step["type"]
        if step_type == "arm_named_action":
            name = str(step.get("name", ""))
            if name not in allowed_actions:
                raise PhotoPlanValidationError("ARM_ACTION_NOT_ALLOWED", f"arm action is not allowlisted: {name}")
            if int(step.get("timeout_s", max_arm_timeout)) > max_arm_timeout:
                raise PhotoPlanValidationError("ARM_TIMEOUT_LIMIT_EXCEEDED", "arm action timeout exceeds policy")
            if name.startswith("camera_"):
                camera_pose_count += 1
        elif step_type == "capture_photo":
            capture_count += 1
            target = str(step.get("target", plan.get("target", "workspace")))
            if target not in allowed_targets:
                raise PhotoPlanValidationError("TARGET_NOT_ALLOWED", f"target is not allowlisted: {target}")
            if int(step.get("timeout_s", max_capture_timeout)) > max_capture_timeout:
                raise PhotoPlanValidationError("CAMERA_TIMEOUT_LIMIT_EXCEEDED", "capture timeout exceeds policy")
        elif step_type == "verify_photo_differences":
            has_verification = True
            if float(step.get("min_difference_score", min_difference_score)) < min_difference_score:
                raise PhotoPlanValidationError(
                    "PHOTO_DIFFERENCE_THRESHOLD_TOO_LOW",
                    "verification threshold is lower than policy minimum",
                )
        elif step_type == "sleep":
            if float(step.get("duration_s", 0)) > max_interval:
                raise PhotoPlanValidationError("PHOTO_INTERVAL_LIMIT_EXCEEDED", "burst interval exceeds policy")

    if capture_count > max_burst_count:
        raise PhotoPlanValidationError("PHOTO_COUNT_LIMIT_EXCEEDED", "burst count exceeds policy")
    if plan.get("intent") == "multi_angle_capture":
        if camera_pose_count > max_pose_count:
            raise PhotoPlanValidationError("PHOTO_POSE_COUNT_LIMIT_EXCEEDED", "multi-angle pose count exceeds policy")
        if bool(multi_angle.get("require_difference_verification", True)) and not has_verification:
            raise PhotoPlanValidationError("PHOTO_VERIFICATION_REQUIRED", "multi-angle capture requires difference verification")
        if bool(multi_angle.get("require_return_home_after_sequence", True)):
            arm_steps = [step for step in plan.get("steps", []) if step["type"] == "arm_named_action"]
            if not arm_steps or arm_steps[-1].get("name") != "arm_home":
                raise PhotoPlanValidationError("ARM_HOME_REQUIRED", "multi-angle capture must return arm_home")


def _classify_risk(plan: dict[str, Any]) -> str:
    if any(step["type"] == "stop" for step in plan.get("steps", [])):
        return "emergency_control"
    if any(step["type"] == "arm_named_action" for step in plan.get("steps", [])):
        return "named_motion"
    return "read_only"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
