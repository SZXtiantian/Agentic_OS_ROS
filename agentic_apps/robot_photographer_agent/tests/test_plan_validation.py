import os
import sys
from pathlib import Path

import pytest


APP_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(APP_DIR))

import planner  # noqa: E402
from planner import plan_task  # noqa: E402
from validation import PhotoPlanValidationError, validate_plan  # noqa: E402


def _llm_plan(**overrides):
    plan = {
        "schema_version": "1.0",
        "plan_id": "plan_llm_test",
        "intent": "before_after_capture",
        "risk_class": "named_motion",
        "requires_motion": True,
        "needs_confirmation": True,
        "planner_mode": "llm",
            "target": "workspace",
        "steps": [
            {"type": "capture_photo", "target": "workspace", "label": "before", "timeout_s": 5},
            {"type": "arm_named_action", "name": "camera_pitch_up_15", "timeout_s": 8},
            {"type": "capture_photo", "target": "workspace", "label": "after_pitch_up_15", "timeout_s": 5},
        ],
        "user_summary": "LLM 规划的前后对比拍照",
    }
    plan.update(overrides)
    return plan


class _FakeLLMChat:
    response = _llm_plan()

    def chat_json(self, *, system_prompt, user_prompt):
        assert "Robot Photographer" in system_prompt
        assert "photo_plan.schema.json" in user_prompt
        return dict(self.response)


def test_read_only_plan_validates():
    plan = plan_task("拍一张照片")
    validated = validate_plan(plan)
    assert validated["risk_class"] == "read_only"
    assert validated["steps"][0]["type"] == "capture_photo"


def test_llm_first_planner_accepts_schema_valid_plan(monkeypatch):
    monkeypatch.setenv("AGENTIC_LLM_ENABLED", "1")

    plan = plan_task("前后对比拍照", llm_chat=_FakeLLMChat())

    assert plan["planner_mode"] == "llm"
    assert plan["intent"] == "before_after_capture"
    assert plan["steps"][1]["name"] == "camera_pitch_up_15"


def test_bad_llm_json_falls_back_to_rule_planner(monkeypatch):
    class BadLLMChat:
        def chat_json(self, *, system_prompt, user_prompt):
            raise RuntimeError("bad json")

    monkeypatch.setenv("AGENTIC_LLM_ENABLED", "1")

    plan = plan_task("拍一张照片", llm_chat=BadLLMChat())

    assert plan["planner_mode"] == "rule_based"
    assert plan["intent"] == "capture_photo"


def test_required_llm_planner_does_not_fallback_to_rule_based(monkeypatch):
    class BadLLMChat:
        def chat_json(self, *, system_prompt, user_prompt):
            raise RuntimeError("network down")

    monkeypatch.setenv("AGENTIC_LLM_ENABLED", "1")

    with pytest.raises(RuntimeError):
        plan_task({"text": "拍一张照片", "require_llm": True}, llm_chat=BadLLMChat())


def test_llm_schema_invalid_falls_back_to_rule_planner(monkeypatch):
    class InvalidPlanClient:
        def chat_json(self, *, system_prompt, user_prompt):
            return {"intent": "capture_photo"}

    monkeypatch.setenv("AGENTIC_LLM_ENABLED", "1")

    plan = plan_task("状态", llm_chat=InvalidPlanClient())

    assert plan["planner_mode"] == "rule_based"
    assert plan["intent"] == "status"


def test_schema_valid_llm_motion_is_policy_rejected_without_permission(monkeypatch):
    class MotionLLMClient:
        def chat_json(self, *, system_prompt, user_prompt):
            return _llm_plan(
                intent="move_camera_pose",
                steps=[
                    {"type": "arm_named_action", "name": "camera_pitch_up_15", "timeout_s": 8},
                    {"type": "capture_photo", "target": "workspace", "label": "after_pitch_up_15", "timeout_s": 5},
                ],
            )

    monkeypatch.setenv("AGENTIC_LLM_ENABLED", "1")
    monkeypatch.delenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", raising=False)

    plan = plan_task("把相机抬起来再拍一张", llm_chat=MotionLLMClient())
    with pytest.raises(PhotoPlanValidationError) as exc:
        validate_plan(plan, allow_arm_motion=False, assume_yes=True)

    assert exc.value.code == "ARM_MOTION_DISABLED"


def test_policy_rejects_unsafe_motion_without_env_or_flag(monkeypatch):
    monkeypatch.delenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", raising=False)
    plan = plan_task("把相机抬起来再拍一张")
    with pytest.raises(PhotoPlanValidationError) as exc:
        validate_plan(plan, allow_arm_motion=False, assume_yes=True)
    assert exc.value.code == "ARM_MOTION_DISABLED"


def test_motion_requires_confirmation(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    plan = plan_task("把相机抬起来再拍一张")
    with pytest.raises(PhotoPlanValidationError) as exc:
        validate_plan(plan, allow_arm_motion=True, assume_yes=False)
    assert exc.value.code == "ARM_CONFIRMATION_REQUIRED"


def test_motion_validates_with_env_and_confirmation(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    plan = plan_task("把相机抬起来再拍一张")
    validated = validate_plan(plan, allow_arm_motion=True, assume_yes=True)
    assert validated["risk_class"] == "named_motion"
    assert validated["steps"][0]["name"] == "camera_pitch_up_15"


def test_before_after_capture_plans_motion_gate(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    plan = plan_task("前后对比拍照")
    validated = validate_plan(plan, allow_arm_motion=True, assume_yes=True)
    assert validated["intent"] == "before_after_capture"
    assert [step["type"] for step in validated["steps"]] == [
        "capture_photo",
        "arm_named_action",
        "capture_photo",
    ]
    assert validated["steps"][1]["name"] == "camera_pitch_up_15"


def test_multi_angle_plan_validates_with_verification_and_home(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    plan = plan_task("拍一组多角度照片并验证差异")
    validated = validate_plan(plan, allow_arm_motion=True, assume_yes=True)
    assert validated["intent"] == "multi_angle_capture"
    assert any(step["type"] == "verify_photo_differences" for step in validated["steps"])
    assert [step for step in validated["steps"] if step["type"] == "arm_named_action"][-1]["name"] == "arm_home"


def test_natural_center_left_right_up_sentence_plans_multi_angle(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    plan = plan_task("从中间、左边、右边、上面拍照并验证差异")
    validated = validate_plan(plan, allow_arm_motion=True, assume_yes=True)
    names = [step["name"] for step in validated["steps"] if step["type"] == "arm_named_action"]
    assert validated["intent"] == "multi_angle_capture"
    assert names == [
        "camera_center",
        "camera_yaw_left_15",
        "camera_yaw_right_15",
        "camera_pitch_up_15",
        "arm_home",
    ]


def test_left_right_plan_uses_yaw_named_actions(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    plan = plan_task("左右各拍一张并验证不同")
    validated = validate_plan(plan, allow_arm_motion=True, assume_yes=True)
    names = [step["name"] for step in validated["steps"] if step["type"] == "arm_named_action"]
    assert "camera_yaw_left_15" in names
    assert "camera_yaw_right_15" in names


def test_up_down_plan_rejects_unverified_pitch_down(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    plan = plan_task("上下角度各拍一张")
    assert plan["intent"] == "unsupported"
    assert plan["risk_class"] == "read_only"
    assert plan["steps"] == [{"type": "status"}]
    assert "camera_pitch_down" in plan["user_summary"]
    with pytest.raises(PhotoPlanValidationError) as exc:
        validate_plan(plan, allow_arm_motion=True, assume_yes=True)
    assert exc.value.code == "PHOTO_INTENT_UNSUPPORTED"


def test_rejects_unsafe_arm_action():
    plan = plan_task("拍一张照片")
    plan["risk_class"] = "named_motion"
    plan["requires_motion"] = True
    plan["needs_confirmation"] = True
    plan["steps"] = [{"type": "arm_named_action", "name": "wave", "timeout_s": 8}]
    with pytest.raises(PhotoPlanValidationError) as exc:
        validate_plan(plan, allow_arm_motion=True, assume_yes=True)
    assert exc.value.code in {"PHOTO_PLAN_INVALID", "ARM_ACTION_NOT_ALLOWED"}


def test_rejects_llm_raw_angle_or_servo_fields():
    plan = plan_task("拍一张照片")
    plan["intent"] = "multi_angle_capture"
    plan["risk_class"] = "named_motion"
    plan["requires_motion"] = True
    plan["needs_confirmation"] = True
    plan["steps"] = [
        {"type": "arm_named_action", "name": "camera_yaw_left_15", "timeout_s": 8, "angle_deg": 15},
        {"type": "capture_photo", "target": "workspace", "label": "left", "timeout_s": 5},
        {"type": "verify_photo_differences", "method": "deterministic_cv_metrics", "min_difference_score": 0.08},
        {"type": "arm_named_action", "name": "arm_home", "timeout_s": 8},
    ]
    with pytest.raises(PhotoPlanValidationError) as exc:
        validate_plan(plan, allow_arm_motion=True, assume_yes=True)
    assert exc.value.code == "PHOTO_PLAN_INVALID"


def test_burst_count_limit_rejects_fake_success():
    plan = plan_task("拍一张照片")
    plan["intent"] = "capture_burst"
    plan["steps"] = [
        {"type": "capture_photo", "target": "workspace", "label": f"p{i}", "timeout_s": 5}
        for i in range(6)
    ]
    with pytest.raises(PhotoPlanValidationError) as exc:
        validate_plan(plan)
    assert exc.value.code in {"PHOTO_PLAN_INVALID", "PHOTO_COUNT_LIMIT_EXCEEDED"}


def test_no_rclpy_or_direct_ros_patterns_in_app_source():
    forbidden = [
        "import " + "rclpy",
        "from " + "rclpy",
        "/" + "cmd_vel",
        "/" + "scan",
        "/" + "odom",
        "/" + "tf",
        "/" + "servo_controller",
        "/" + "depth_cam",
        "/" + "kinematics",
        "MoveIt",
        "Nav2",
        "ActionClient",
        "create_publisher",
        "create_subscription",
    ]
    for path in APP_DIR.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in text


def test_app_planner_does_not_construct_llm_provider_client():
    text = (APP_DIR / "planner.py").read_text(encoding="utf-8")
    assert "OpenAICompatibleChatClient" not in text
    assert "load_llm_config" not in text
    assert "AGENTIC_LLM_API_KEY" not in text
