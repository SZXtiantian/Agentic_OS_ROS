import json
from pathlib import Path

import yaml


APP_DIR = Path(__file__).parents[1]


def test_aios_manifest_describes_agent_package():
    config = json.loads((APP_DIR / "config.json").read_text(encoding="utf-8"))
    assert config["name"] == "robot_photographer_agent"
    assert config["build"]["entry"] == "entry.py"
    assert config["build"]["module"] == "RobotPhotographerAgent"
    assert "agenticos/perception_capture_photo" in config["tools"]
    assert "agenticos/llm_chat" in config["tools"]


def test_app_yaml_describes_robot_policy():
    manifest = yaml.safe_load((APP_DIR / "app.yaml").read_text(encoding="utf-8"))
    assert manifest["runtime_type"] == "aios_agent_package"
    assert "perception.capture_photo" in manifest["required_capabilities"]
    assert "llm.chat" in manifest["required_capabilities"]
    assert manifest["runtime_limits"]["llm_planning_provider"] == "agenticos.runtime.llm_chat"
    assert "arm.move.named" in manifest["permissions"]
    assert manifest["allowed_targets"] == ["workspace"]
    assert set(manifest["allowed_arm_actions"]) == {
        "arm_home",
        "camera_center",
        "camera_yaw_left_15",
        "camera_yaw_right_15",
        "camera_pitch_up_15",
    }
    assert manifest["evidence"]["role"] == "runtime_raw_evidence"
    assert manifest["app_storage"]["root"] == "storage"
    assert manifest["app_storage"]["photos"] == "storage/photos"
    assert manifest["app_storage"]["role"] == "app_owned_user_outputs"
