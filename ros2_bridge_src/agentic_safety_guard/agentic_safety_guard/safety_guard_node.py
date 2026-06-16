import json
import time
from pathlib import Path

import rclpy
import yaml
from agentic_msgs.srv import CheckSafety, StopRobot
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from .config_paths import default_config_path


DEFAULT_PROFILE = Path("/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml")


class SafetyGuardNode(Node):
    def __init__(self) -> None:
        super().__init__("safety_guard_node")
        self.declare_parameter("safety_file", str(default_config_path("safety.yaml")))
        self.declare_parameter("places_file", str(default_config_path("places.yaml")))
        self.declare_parameter("bridge_profile_file", str(DEFAULT_PROFILE))
        self.declare_parameter("estop_pressed", False)
        self._callback_group = ReentrantCallbackGroup()
        self._safety = self._load_yaml(Path(self.get_parameter("safety_file").value)).get("safety", {})
        self._places = self._load_yaml(Path(self.get_parameter("places_file").value)).get("places", {})
        self._profile = self._load_yaml(Path(self.get_parameter("bridge_profile_file").value))
        self._arm_stop_client = self.create_client(StopRobot, "/agentic/arm/stop", callback_group=self._callback_group)
        self.create_service(CheckSafety, "/agentic/safety/check", self.check_safety, callback_group=self._callback_group)
        self.create_service(StopRobot, "/agentic/robot/stop", self.stop_robot, callback_group=self._callback_group)
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

        if request.skill_name in {"perception.observe", "observe", "perception.capture_photo", "capture_photo"}:
            target = str(args.get("target", "workspace"))
            camera = dict(self._safety.get("camera") or {})
            allowed_targets = set(str(item) for item in camera.get("allowed_targets", []))
            if allowed_targets and target not in allowed_targets and target not in self._places:
                response.allowed = False
                response.error_code = "CAMERA_TARGET_NOT_ALLOWED"
                response.reason = f"camera target is not allowlisted: {target}"
                return response
            max_observe = int(camera.get("max_observe_duration_s", 10))
            max_capture = int(camera.get("max_capture_duration_s", max_observe))
            max_duration = max_capture if request.skill_name in {"perception.capture_photo", "capture_photo"} else max_observe
            timeout_s = int(args.get("timeout_s") or max_duration)
            if timeout_s > max_duration:
                response.allowed = False
                response.error_code = "CAMERA_TIMEOUT_LIMIT_EXCEEDED"
                response.reason = f"camera timeout {timeout_s}s exceeds max {max_duration}s"
                return response

        if request.skill_name in {"robot.inspect_area", "inspect_area"}:
            place_name = str(args.get("place", ""))
            if place_name and place_name not in self._places:
                response.allowed = False
                response.error_code = "PLACE_NOT_FOUND"
                response.reason = f"unknown place: {place_name}"
                return response
            camera = dict(self._safety.get("camera") or {})
            max_observe = int(camera.get("max_observe_duration_s", 10))
            timeout_s = int(args.get("timeout_s") or max_observe)
            if timeout_s > max_observe:
                response.allowed = False
                response.error_code = "CAMERA_TIMEOUT_LIMIT_EXCEEDED"
                response.reason = f"inspect timeout {timeout_s}s exceeds max {max_observe}s"
                return response

        if request.skill_name in {"arm.move_named", "move_named"}:
            manipulation = dict(self._safety.get("manipulation") or {})
            allowed = set(str(item) for item in manipulation.get("allowed_named_actions", []))
            name = self._canonical_arm_action(str(args.get("name") or args.get("action") or ""))
            profile_allowed = set((self._profile.get("arm") or {}).get("allowed_named_actions", {}).keys())
            if name not in allowed or (profile_allowed and name not in profile_allowed):
                response.allowed = False
                response.error_code = "ARM_ACTION_NOT_ALLOWED"
                response.reason = f"arm action is not allowlisted: {name}"
                return response
            max_duration = int(manipulation.get("max_arm_duration_s", 8))
            timeout_s = int(args.get("timeout_s") or max_duration)
            if timeout_s > max_duration:
                response.allowed = False
                response.error_code = "ARM_TIMEOUT_LIMIT_EXCEEDED"
                response.reason = f"arm timeout {timeout_s}s exceeds max {max_duration}s"
                return response

        if request.skill_name in {"gripper.set", "set_gripper"}:
            manipulation = dict(self._safety.get("manipulation") or {})
            command = str(args.get("command", "")).strip()
            force = str(args.get("force", "low")).strip() or "low"
            allowed_commands = set(str(item) for item in manipulation.get("allowed_gripper_commands", []))
            allowed_forces = set(str(item) for item in manipulation.get("allowed_gripper_forces", []))
            canonical_command = "open" if command == "open_gripper" else "close" if command == "close_gripper_low_force" else command
            if canonical_command not in allowed_commands:
                response.allowed = False
                response.error_code = "GRIPPER_COMMAND_NOT_ALLOWED"
                response.reason = f"gripper command is not allowlisted: {command}"
                return response
            if force not in allowed_forces:
                response.allowed = False
                response.error_code = "GRIPPER_FORCE_NOT_ALLOWED"
                response.reason = f"gripper force is not allowlisted: {force}"
                return response
            percentage = args.get("percentage")
            if percentage is not None and (float(percentage) < 0.0 or float(percentage) > 100.0):
                response.allowed = False
                response.error_code = "GRIPPER_RANGE_INVALID"
                response.reason = "gripper percentage must be in [0, 100]"
                return response

        response.allowed = True
        response.error_code = ""
        response.reason = ""
        return response

    def stop_robot(self, request: StopRobot.Request, response: StopRobot.Response):
        self.get_logger().warning(f"stop requested: {request.reason} ({request.request_id})")
        arm_stop = self._call_arm_stop(request)
        response.success = bool(arm_stop.get("success", False))
        response.error_code = str(arm_stop.get("error_code", ""))
        response.message = json.dumps(
            {
                "safety_guard": "stop accepted",
                "reason": request.reason,
                "request_id": request.request_id,
                "arm_stop": arm_stop,
            },
            ensure_ascii=False,
        )
        return response

    def _call_arm_stop(self, request: StopRobot.Request) -> dict:
        if not self._arm_stop_client.wait_for_service(timeout_sec=0.2):
            return {
                "success": False,
                "error_code": "STOP_BACKEND_UNAVAILABLE",
                "message": "arm stop service unavailable: /agentic/arm/stop",
            }
        arm_request = StopRobot.Request()
        arm_request.reason = request.reason
        arm_request.request_id = request.request_id
        future = self._arm_stop_client.call_async(arm_request)
        started = time.monotonic()
        while not future.done() and time.monotonic() - started < 2.0:
            time.sleep(0.02)
        if not future.done():
            return {
                "success": False,
                "error_code": "STOP_BACKEND_TIMEOUT",
                "message": "timed out waiting for /agentic/arm/stop",
            }
        result = future.result()
        if result is None:
            return {"success": False, "error_code": "STOP_BACKEND_UNAVAILABLE", "message": "arm stop returned no result"}
        message = str(result.message)
        parsed = {}
        try:
            parsed = json.loads(message)
        except json.JSONDecodeError:
            parsed = {"message": message}
        return {
            "success": bool(result.success),
            "error_code": str(result.error_code),
            "message": message,
            "detail": parsed,
        }

    def _canonical_arm_action(self, name: str) -> str:
        return {"home": "arm_home", "init": "arm_home", "camera_up": "camera_pitch_up_15"}.get(name.strip(), name.strip())


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SafetyGuardNode()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
