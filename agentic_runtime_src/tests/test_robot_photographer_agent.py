import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

from agentic_os.kernel.access import AlwaysAllowTestInterventionProvider
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


APP_DIR = Path(os.environ["AGENTIC_APP_ROOT"]) / "robot_photographer_agent"


def _load_entry():
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    spec = importlib.util.spec_from_file_location("robot_photographer_agent.entry", APP_DIR / "entry.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_aios_manifest_and_app_policy_load():
    config = json.loads((APP_DIR / "config.json").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((APP_DIR / "app.yaml").read_text(encoding="utf-8"))
    assert config["build"]["module"] == "RobotPhotographerAgent"
    assert "agenticos/perception_capture_photo" in config["tools"]
    assert manifest["runtime_type"] == "aios_agent_package"
    assert "perception.capture_photo" in manifest["required_capabilities"]
    assert manifest["allowed_targets"] == ["workspace"]


def test_entry_loads_and_motion_rejected_without_permission(monkeypatch):
    monkeypatch.delenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", raising=False)
    module = _load_entry()
    server = create_test_runtime_server()
    agent = module.RobotPhotographerAgent(runtime=server)
    result = agent.run({"text": "把相机抬起来再拍一张"})
    assert result["success"] is False
    assert result["error_code"] == "ARM_MOTION_DISABLED"


def test_entry_rejects_simulated_task_field_even_with_runtime():
    module = _load_entry()
    server = create_test_runtime_server()
    agent = module.RobotPhotographerAgent(runtime=server)
    result = agent.run({"text": "拍一张照片", "mock": True})
    assert result["success"] is False
    assert result["error_code"] == "TASK_INPUT_FIELD_UNSUPPORTED"
    assert server.test_bridge_calls == []


def test_read_only_robot_photographer_reports_missing_camera_bridge(tmp_path, monkeypatch):
    evidence_root = tmp_path / "photos"
    app_storage = tmp_path / "app_storage"
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT", str(app_storage))

    async def run():
        module = _load_entry()
        server = create_test_runtime_server()
        server.kernel_service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()
        agent = module.RobotPhotographerAgent(runtime=server)
        result = await agent.arun({"text": "拍一张照片"})
        app_result = result["result"]
        assert result["status"] == "failed"
        assert app_result["success"] is False
        assert app_result["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert app_result["steps"] == []
        assert not (app_storage / "indexes" / "photos.jsonl").exists()
        assert any(record.get("skill_name") == "perception.capture_photo" for record in server.audit_logger.recent(limit=20))
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/safety/check"
        session = server.session_manager.get_session(result["session_id"])
        assert session is not None
        assert "mock" not in session.task["task_input"]
        recent = await agent.arun({"text": "查看最近照片"})
        photos = recent["result"]["steps"][0]["photos"]
        assert photos == []

    asyncio.run(run())


def test_motion_requires_confirmation_even_with_env(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    module = _load_entry()
    server = create_test_runtime_server()
    agent = module.RobotPhotographerAgent(runtime=server)
    result = agent.run({"text": "把相机抬起来再拍一张", "allow_arm_motion": True})
    assert result["success"] is False
    assert result["error_code"] == "ARM_CONFIRMATION_REQUIRED"


def test_motion_allowed_with_env_flag_and_confirmation(monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")

    async def run():
        module = _load_entry()
        server = create_test_runtime_server()
        server.kernel_service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()
        agent = module.RobotPhotographerAgent(runtime=server)
        result = await agent.arun(
            {
                "text": "把相机抬起来再拍一张",
                "allow_arm_motion": True,
                "assume_yes": True,
            }
        )
        app_result = result["result"]
        assert app_result["success"] is False
        assert app_result["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert app_result["steps"] == []
        assert app_result["stop_result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/safety/check"
        assert server.test_bridge_calls[-1]["command"][3] == "/agentic/robot/stop"

    asyncio.run(run())


def test_multi_angle_capture_reports_missing_robot_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    app_storage = tmp_path / "app_storage"
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path / "photos"))
    monkeypatch.setenv("AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT", str(app_storage))

    async def run():
        module = _load_entry()
        server = create_test_runtime_server()
        server.kernel_service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()
        agent = module.RobotPhotographerAgent(runtime=server)
        result = await agent.arun(
            {
                "text": "拍一组多角度照片并验证差异",
                "allow_arm_motion": True,
                "assume_yes": True,
            }
        )
        app_result = result["result"]
        assert app_result["success"] is False
        assert app_result["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert app_result["steps"] == []
        assert app_result["stop_result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert not (app_storage / "runs" / result["session_id"] / "verification.json").exists()
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/safety/check"

    asyncio.run(run())


def test_multi_angle_verification_failure_still_runs_arm_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "1")
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path / "photos"))
    monkeypatch.setenv("AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT", str(tmp_path / "app_storage"))

    async def run():
        server = create_test_runtime_server()
        server.kernel_service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()
        spec = importlib.util.spec_from_file_location("robot_photographer_agent.main", APP_DIR / "main.py")
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        app = AppManifest(
            name="robot_photographer_agent",
            version="0",
            description="",
            entrypoint="main:run",
            permissions=["perception.capture", "arm.move.named", "memory.write"],
            required_capabilities=["perception.capture_photo", "arm.move_named", "memory.remember"],
        )
        ctx = AgentContext(server.executor, app, "sess_photo_cleanup")
        plan = {
            "schema_version": "1.0",
            "plan_id": "plan_cleanup",
            "intent": "multi_angle_capture",
            "risk_class": "named_motion",
            "requires_motion": True,
            "planner_mode": "rule_based",
            "user_summary": "cleanup test",
            "validated": True,
            "steps": [
                {"type": "arm_named_action", "name": "camera_center", "timeout_s": 8},
                {"type": "capture_photo", "target": "workspace", "label": "center", "timeout_s": 5},
                {"type": "arm_named_action", "name": "camera_yaw_left_15", "timeout_s": 8},
                {"type": "capture_photo", "target": "workspace", "label": "left", "timeout_s": 5},
                {"type": "verify_photo_differences", "method": "deterministic_cv_metrics", "min_difference_score": 1.0},
                {"type": "arm_named_action", "name": "arm_home", "timeout_s": 8},
            ],
        }
        result = await module.execute_plan(ctx, plan)
        assert result["success"] is False
        assert result["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert result["steps"] == []
        assert result["stop_result"]["error_code"] == "PERMISSION_DENIED"

    asyncio.run(run())


def test_skill_registry_includes_capture_and_recent_photos():
    server = create_test_runtime_server()
    names = {skill.name for skill in server.registry.list_skills()}
    assert "perception.capture_photo" in names
    assert "storage.list_recent_photos" in names


def test_tool_wrapper_does_not_import_ros():
    path = Path(os.environ["AGENTIC_RUNTIME_SRC"]) / "agentic_runtime" / "agenticos_tools.py"
    text = path.read_text(encoding="utf-8")
    forbidden = ["import rclpy", "from rclpy", "/servo_controller", "/depth_cam", "ActionClient"]
    for pattern in forbidden:
        assert pattern not in text


def test_app_source_has_no_direct_ros_patterns():
    forbidden = [
        "import rclpy",
        "from rclpy",
        "/cmd_vel",
        "/scan",
        "/odom",
        "/tf",
        "/servo_controller",
        "/depth_cam",
        "/kinematics",
        "MoveIt",
        "Nav2",
        "ActionClient",
        "create_publisher",
        "create_subscription",
    ]
    for path in APP_DIR.rglob("*.py"):
        if "tests" in path.relative_to(APP_DIR).parts:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in text, f"{path} contains {pattern}"


def test_photo_plan_schema_validation():
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    from planner import plan_task
    from validation import PhotoPlanValidationError, validate_plan

    plan = plan_task("拍一张照片")
    assert validate_plan(plan)["risk_class"] == "read_only"
    plan["target"] = "kitchen"
    with pytest.raises(PhotoPlanValidationError) as exc:
        validate_plan(plan)
    assert exc.value.code in {"PHOTO_PLAN_INVALID", "TARGET_NOT_ALLOWED"}
