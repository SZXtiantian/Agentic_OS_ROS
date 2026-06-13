import json
from pathlib import Path

import rclpy
import yaml
from agentic_msgs.srv import CheckSafety, StopRobot
from rclpy.node import Node

from .config_paths import default_config_path


class SafetyGuardNode(Node):
    def __init__(self) -> None:
        super().__init__("safety_guard_node")
        self.declare_parameter("safety_file", str(default_config_path("safety.yaml")))
        self.declare_parameter("places_file", str(default_config_path("places.yaml")))
        self.declare_parameter("estop_pressed", False)
        self._safety = self._load_yaml(Path(self.get_parameter("safety_file").value)).get("safety", {})
        self._places = self._load_yaml(Path(self.get_parameter("places_file").value)).get("places", {})
        self.create_service(CheckSafety, "/agentic/safety/check", self.check_safety)
        self.create_service(StopRobot, "/agentic/robot/stop", self.stop_robot)
        self.get_logger().info("agentic safety guard ready")

    def _load_yaml(self, path: Path) -> dict:
        if not path.exists():
            self.get_logger().warning(f"config file not found: {path}")
            return {}
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def check_safety(self, request: CheckSafety.Request, response: CheckSafety.Response):
        if bool(self.get_parameter("estop_pressed").value):
            response.allowed = False
            response.error_code = "ESTOP_PRESSED"
            response.reason = "estop is pressed"
            return response

        args = {}
        if request.args_json:
            try:
                args = json.loads(request.args_json)
            except json.JSONDecodeError:
                response.allowed = False
                response.error_code = "SCHEMA_INVALID"
                response.reason = "args_json is not valid JSON"
                return response

        if request.skill_name in {"navigate_to", "robot.navigate_to"}:
            place_name = args.get("place", "")
            place = self._places.get(place_name)
            forbidden = set(self._safety.get("forbidden_zones", []))
            if place is None:
                response.allowed = False
                response.error_code = "PLACE_NOT_FOUND"
                response.reason = f"unknown place: {place_name}"
                return response
            if not bool(place.get("allowed", True)) or str(place.get("id", "")) in forbidden:
                response.allowed = False
                response.error_code = "FORBIDDEN_ZONE"
                response.reason = f"place is forbidden: {place_name}"
                return response

        response.allowed = True
        response.error_code = ""
        response.reason = ""
        return response

    def stop_robot(self, request: StopRobot.Request, response: StopRobot.Response):
        self.get_logger().warning(f"stop requested: {request.reason} ({request.request_id})")
        response.success = True
        response.error_code = ""
        response.message = "stop accepted by safety guard"
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SafetyGuardNode()
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
