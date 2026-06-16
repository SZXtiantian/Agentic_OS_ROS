import pytest

from agentic_runtime.dispatcher.app_index import AppIndex
from agentic_runtime.dispatcher.errors import DispatchError
from agentic_runtime.dispatcher.planner import DispatcherPlanner
from agentic_runtime.dispatcher.validation import DispatcherValidator
from agentic_runtime.nl_gateway import GatewayFlags


def _validate_text(text: str, flags=None):
    app_index = AppIndex.load("/home/ubuntu/agentic_ws/src")
    plan = DispatcherPlanner().plan(
        text,
        app_index,
        flags or GatewayFlags(mock=True),
        task_id="task_test",
        route_plan_id="plan_route_test",
    )
    return DispatcherValidator().validate(plan, app_index, flags or GatewayFlags(mock=True))


def test_downward_camera_request_rejected():
    with pytest.raises(DispatchError) as exc:
        _validate_text("向下拍一张")
    assert exc.value.code == "DISPATCH_UNSAFE_REQUEST_REJECTED"


def test_direct_ros_request_rejected():
    with pytest.raises(DispatchError) as exc:
        _validate_text("用 /cmd_vel 直接控制机器人")
    assert exc.value.code == "DISPATCH_UNSAFE_REQUEST_REJECTED"


def test_motion_rejected_without_env_or_flag(monkeypatch):
    monkeypatch.delenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", raising=False)
    with pytest.raises(DispatchError) as exc:
        _validate_text("从中间、左边、右边、上面拍照并验证差异")
    assert exc.value.code == "DISPATCH_MOTION_DISABLED"


def test_motion_requires_confirmation_with_flag(monkeypatch):
    monkeypatch.delenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", raising=False)
    with pytest.raises(DispatchError) as exc:
        _validate_text(
            "从中间、左边、右边、上面拍照并验证差异",
            GatewayFlags(mock=True, allow_arm_motion=True),
        )
    assert exc.value.code == "DISPATCH_CONFIRMATION_REQUIRED"


def test_motion_validates_with_flag_and_yes(monkeypatch):
    monkeypatch.delenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", raising=False)
    validated = _validate_text(
        "从中间、左边、右边、上面拍照并验证差异",
        GatewayFlags(mock=True, allow_arm_motion=True, assume_yes=True),
    )
    assert validated["risk_class"] == "named_motion"


def test_unknown_app_rejected():
    app_index = AppIndex.load("/home/ubuntu/agentic_ws/src")
    plan = DispatcherPlanner().plan("拍一张照片", app_index, GatewayFlags(mock=True), task_id="task_test", route_plan_id="plan_route_test")
    plan["selected_app_id"] = "missing_app"
    with pytest.raises(DispatchError) as exc:
        DispatcherValidator().validate(plan, app_index, GatewayFlags(mock=True))
    assert exc.value.code in {"DISPATCH_LLM_SCHEMA_INVALID", "DISPATCH_APP_NOT_FOUND"}
