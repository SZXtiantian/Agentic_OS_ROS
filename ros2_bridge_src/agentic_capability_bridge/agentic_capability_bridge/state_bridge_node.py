import json
from pathlib import Path
from typing import Any

import rclpy
import yaml
from agentic_msgs.srv import GetRobotState
from rclpy.node import Node


DEFAULT_PROFILE = Path("/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml")
DIRECT_ACTION_GROUP_BACKENDS = {"servo_action_group", "action_group_controller", "vendor_action_group_file"}


class StateBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("state_bridge_node")
        self.declare_parameter("robot_id", "mock_robot")
        self.declare_parameter("mode", "mock")
        self.declare_parameter("battery_percent", 80.0)
        self.declare_parameter("current_place", "")
        self.declare_parameter("bridge_profile_file", str(DEFAULT_PROFILE))
        self._profile = self._load_profile()
        self.create_service(GetRobotState, "/agentic/robot/get_state", self.get_robot_state)
        self.get_logger().info("agentic state bridge ready")

    def _load_profile(self) -> dict[str, Any]:
        path = Path(str(self.get_parameter("bridge_profile_file").value)).expanduser()
        if not path.exists():
            self.get_logger().warning(f"bridge profile not found: {path}")
            return {}
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def get_robot_state(self, request: GetRobotState.Request, response: GetRobotState.Response):
        del request
        response.success = True
        response.error_code = ""
        response.reason = ""
        response.state.robot_id = str(self.get_parameter("robot_id").value)
        response.state.mode = str(self.get_parameter("mode").value)
        response.state.battery_state = "normal"
        response.state.battery_percent = float(self.get_parameter("battery_percent").value)
        response.state.is_localized = True
        response.state.is_moving = False
        response.state.estop_pressed = False
        response.state.current_place = str(self.get_parameter("current_place").value)
        response.state.active_task_id = ""
        response.state.state_json = json.dumps(self._bridge_readiness(response.state.mode), ensure_ascii=False)
        return response

    def _bridge_readiness(self, mode: str) -> dict[str, Any]:
        topics = {name for name, _types in self.get_topic_names_and_types()}
        services = {name for name, _types in self.get_service_names_and_types()}
        camera = dict(self._profile.get("camera") or {})
        arm = dict(self._profile.get("arm") or {})
        gripper = dict(self._profile.get("gripper") or {})
        camera_topics = [
            str(camera.get("primary_rgb_topic") or ""),
            *[str(topic) for topic in camera.get("fallback_rgb_topics", [])],
        ]
        camera_topics = [topic for topic in camera_topics if topic]
        arm_backend_type = str(arm.get("backend_type") or "")
        arm_command_topic = str(arm.get("action_command_topic") or "")
        arm_status_service = str(arm.get("action_status_service") or "")
        gripper_topic = str(gripper.get("servo_command_topic") or "")
        action_files_available = self._action_files_available(arm)
        if arm_backend_type in DIRECT_ACTION_GROUP_BACKENDS:
            arm_backend_available = bool(arm_command_topic and arm_command_topic in topics and all(action_files_available.values()))
        else:
            arm_backend_available = bool(
                arm_command_topic
                and arm_command_topic in topics
                and arm_status_service
                and arm_status_service in services
            )
        return {
            "source": "state_bridge_node",
            "mode": mode,
            "profile_name": self._profile.get("profile_name", ""),
            "camera_ready": any(topic in topics for topic in camera_topics),
            "camera_topics": camera_topics,
            "arm_backend_type": arm_backend_type,
            "arm_backend_available": arm_backend_available,
            "arm_command_topic": arm_command_topic,
            "arm_status_service_available": bool(arm_status_service and arm_status_service in services),
            "arm_status_service": arm_status_service,
            "action_group_path": str(arm.get("action_group_path") or ""),
            "action_files_available": action_files_available,
            "gripper_topic_visible": bool(gripper_topic and gripper_topic in topics),
            "gripper_topic": gripper_topic,
        }

    def _action_files_available(self, arm: dict[str, Any]) -> dict[str, bool]:
        action_group_path = Path(str(arm.get("action_group_path") or "/home/ubuntu/software/arm_pc/ActionGroups"))
        allowed = dict(arm.get("allowed_named_actions") or {})
        return {
            str(name): (action_group_path / f"{dict(spec or {}).get('backend_action', name)}.d6a").exists()
            for name, spec in allowed.items()
        }


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StateBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
