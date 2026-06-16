import json
import threading
import time
from pathlib import Path
from typing import Any

import rclpy
import yaml
from agentic_msgs.action import MoveArmNamed
from agentic_msgs.srv import GetArmState, SetGripper, StopRobot
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from servo_controller_msgs.msg import ServoPosition, ServosPosition
from std_msgs.msg import String
from std_srvs.srv import Trigger

try:
    from servo_controller.action_group_controller import ActionGroupController
except Exception:  # pragma: no cover - depends on robot ROS overlay
    ActionGroupController = None


DEFAULT_PROFILE = Path("/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml")
DIRECT_ACTION_GROUP_BACKENDS = {"servo_action_group", "action_group_controller", "vendor_action_group_file"}


class ManipulationBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("manipulation_bridge_node")
        self.declare_parameter("bridge_profile_file", str(DEFAULT_PROFILE))
        self._profile = self._load_profile()
        self._callback_group = ReentrantCallbackGroup()
        self._lock = threading.Lock()
        self._direct_action_lock = threading.Lock()
        self._direct_action_controller = None
        self._active_action = ""
        self._active_backend_action = ""
        self._last_gripper_command = ""
        self._gripper_pub = self.create_publisher(ServosPosition, self._gripper_topic(), 10)
        if self._uses_direct_action_group():
            self._arm_command_pub = None
        else:
            self._arm_command_pub = self.create_publisher(String, self._arm_command_topic(), 10)
        status_service = self._arm_status_service()
        self._status_client = (
            self.create_client(Trigger, status_service, callback_group=self._callback_group) if status_service else None
        )
        self._server = ActionServer(
            self,
            MoveArmNamed,
            "/agentic/arm/move_named",
            execute_callback=self.execute_move_named,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self._callback_group,
        )
        self.create_service(GetArmState, "/agentic/arm/get_state", self.get_arm_state, callback_group=self._callback_group)
        self.create_service(SetGripper, "/agentic/gripper/set", self.set_gripper, callback_group=self._callback_group)
        self.create_service(StopRobot, "/agentic/arm/stop", self.stop_arm, callback_group=self._callback_group)
        self.get_logger().info("agentic manipulation bridge ready")

    def _load_profile(self) -> dict[str, Any]:
        path = Path(str(self.get_parameter("bridge_profile_file").value)).expanduser()
        if not path.exists():
            self.get_logger().warning(f"bridge profile not found: {path}")
            return {}
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _arm_profile(self) -> dict[str, Any]:
        return dict(self._profile.get("arm") or {})

    def _gripper_profile(self) -> dict[str, Any]:
        return dict(self._profile.get("gripper") or {})

    def _arm_backend_type(self) -> str:
        return str(self._arm_profile().get("backend_type") or "openclaw_action_group")

    def _uses_direct_action_group(self) -> bool:
        return self._arm_backend_type() in DIRECT_ACTION_GROUP_BACKENDS

    def _arm_command_topic(self) -> str:
        if "action_command_topic" in self._arm_profile():
            return str(self._arm_profile().get("action_command_topic") or "")
        if self._uses_direct_action_group():
            return self._gripper_topic()
        return "/claw_arm_group_control/arm_group_control"

    def _arm_status_service(self) -> str:
        if "action_status_service" in self._arm_profile():
            return str(self._arm_profile().get("action_status_service") or "")
        if self._uses_direct_action_group():
            return ""
        return "/claw_arm_group_control/arm_group_status"

    def _gripper_topic(self) -> str:
        return str(self._gripper_profile().get("servo_command_topic") or "/servo_controller")

    def _max_arm_duration_s(self) -> int:
        return int(self._arm_profile().get("max_duration_s", 8))

    def goal_callback(self, goal_request):
        name = self._canonical_action_name(str(goal_request.name))
        if name not in self._allowed_named_actions():
            self.get_logger().warning(f"rejecting non-allowlisted arm action: {goal_request.name}")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        del goal_handle
        self.get_logger().warning("arm action cancel requested")
        return CancelResponse.ACCEPT

    def get_arm_state(self, request: GetArmState.Request, response: GetArmState.Response):
        del request
        backend_available = self._arm_backend_available()
        gripper_ready = self._gripper_pub.get_subscription_count() > 0
        with self._lock:
            active_action = self._active_action
        response.success = True
        response.error_code = ""
        response.reason = ""
        response.state.readiness = "ready" if backend_available or gripper_ready else "backend_unavailable"
        response.state.active_action = active_action
        response.state.is_moving = bool(active_action)
        response.state.gripper_ready = bool(gripper_ready)
        response.state.stop_available = self._stop_backend_available()
        response.state.state_json = json.dumps(
            {
                "arm_command_topic": self._arm_command_topic(),
                "arm_status_service": self._arm_status_service(),
                "arm_backend_type": self._arm_backend_type(),
                "arm_backend_available": backend_available,
                "action_group_path": self._action_group_path(),
                "action_files_available": self._action_files_available(),
                "camera_pose_actions_available": self._camera_pose_actions_available(),
                "gripper_topic": self._gripper_topic(),
                "gripper_subscribers": self._gripper_pub.get_subscription_count(),
                "last_gripper_command": self._last_gripper_command,
                "stop_backend": self._arm_profile().get("stop_backend", {}),
            },
            ensure_ascii=False,
        )
        return response

    def execute_move_named(self, goal_handle):
        requested_name = str(goal_handle.request.name)
        name = self._canonical_action_name(requested_name)
        action_spec = self._allowed_named_actions().get(name)
        result = MoveArmNamed.Result()
        if action_spec is None:
            goal_handle.abort()
            return self._arm_result(result, False, "ARM_ACTION_NOT_ALLOWED", f"arm action is not allowlisted: {requested_name}", {})

        timeout_s = int(goal_handle.request.timeout_s or action_spec.get("duration_s", self._max_arm_duration_s()))
        if timeout_s > self._max_arm_duration_s():
            goal_handle.abort()
            return self._arm_result(
                result,
                False,
                "ARM_TIMEOUT_LIMIT_EXCEEDED",
                f"requested timeout {timeout_s}s exceeds max {self._max_arm_duration_s()}s",
                {"requested_timeout_s": timeout_s},
            )
        if self._uses_direct_action_group():
            action_file = self._action_group_file(str(action_spec.get("backend_action", name)))
            if not action_file.exists():
                goal_handle.abort()
                return self._arm_result(
                    result,
                    False,
                    self._missing_backend_error_code(name),
                    f"action group file is missing: {action_file}",
                    self._backend_metadata(action_spec),
                )
        if not self._arm_backend_available():
            goal_handle.abort()
            return self._arm_result(
                result,
                False,
                "BACKEND_UNAVAILABLE",
                self._backend_unavailable_reason(action_spec),
                self._backend_metadata(action_spec),
            )

        with self._lock:
            if self._active_action:
                goal_handle.abort()
                return self._arm_result(result, False, "ARM_BUSY", f"active action: {self._active_action}", {})
            self._active_action = name
            self._active_backend_action = str(action_spec.get("backend_action", name))

        started = time.monotonic()
        backend_action = str(action_spec.get("backend_action", name))
        try:
            if self._uses_direct_action_group():
                return self._execute_direct_action_group(goal_handle, result, action_spec, backend_action, timeout_s, started)

            if self._arm_command_pub is None:
                goal_handle.abort()
                return self._arm_result(
                    result,
                    False,
                    "BACKEND_UNAVAILABLE",
                    "arm command publisher is not configured",
                    self._backend_metadata(action_spec),
                )
            self._arm_command_pub.publish(String(data=backend_action))
            feedback = MoveArmNamed.Feedback()
            feedback.status = "running"
            feedback.progress = 0.0
            feedback.feedback_json = json.dumps(self._backend_metadata(action_spec), ensure_ascii=False)
            goal_handle.publish_feedback(feedback)
            time.sleep(0.2)

            while time.monotonic() - started < timeout_s:
                if goal_handle.is_cancel_requested:
                    stop_result = self._stop_active_arm("cancel_requested")
                    if stop_result["success"]:
                        goal_handle.canceled()
                        return self._arm_result(result, False, "SKILL_CANCELLED", "arm action cancelled", stop_result)
                    goal_handle.abort()
                    return self._arm_result(
                        result,
                        False,
                        stop_result["error_code"],
                        stop_result["message"],
                        stop_result,
                    )

                status = self._read_arm_status(timeout_s=0.5)
                elapsed = time.monotonic() - started
                feedback.status = status or "running"
                feedback.progress = float(min(elapsed / max(timeout_s, 0.1), 1.0))
                feedback.feedback_json = json.dumps({"status": status, **self._backend_metadata(action_spec)}, ensure_ascii=False)
                goal_handle.publish_feedback(feedback)
                if status in {"finished", "stop", "idle"}:
                    goal_handle.succeed()
                    return self._arm_result(
                        result,
                        True,
                        "",
                        "",
                        {"status": status, "duration_s": round(elapsed, 3), **self._backend_metadata(action_spec)},
                    )
                time.sleep(0.2)

            stop_result = self._stop_active_arm("arm_action_timeout")
            goal_handle.abort()
            return self._arm_result(
                result,
                False,
                "ARM_ACTION_TIMEOUT",
                f"arm action timed out after {timeout_s}s",
                {"stop_result": stop_result, **self._backend_metadata(action_spec)},
            )
        finally:
            with self._lock:
                self._active_action = ""
                self._active_backend_action = ""

    def _execute_direct_action_group(self, goal_handle, result, action_spec, backend_action: str, timeout_s: int, started: float):
        controller = self._ensure_direct_action_controller()
        if controller is None:
            goal_handle.abort()
            return self._arm_result(
                result,
                False,
                "BACKEND_UNAVAILABLE",
                "servo action group controller is unavailable",
                self._backend_metadata(action_spec),
            )
        action_file = self._action_group_file(backend_action)
        if not action_file.exists():
            goal_handle.abort()
            return self._arm_result(
                result,
                False,
                self._missing_backend_error_code(str(action_spec.get("name", "") or backend_action)),
                f"action group file is missing: {action_file}",
                self._backend_metadata(action_spec),
            )

        errors: list[str] = []

        def run_action() -> None:
            try:
                controller.run_action(backend_action)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                errors.append(str(exc))

        worker = threading.Thread(target=run_action, daemon=True)
        worker.start()
        while worker.is_alive():
            elapsed = time.monotonic() - started
            feedback = MoveArmNamed.Feedback()
            feedback.status = "running"
            feedback.progress = float(min(elapsed / max(timeout_s, 0.1), 1.0))
            feedback.feedback_json = json.dumps(self._backend_metadata(action_spec), ensure_ascii=False)
            goal_handle.publish_feedback(feedback)

            if goal_handle.is_cancel_requested:
                stop_result = self._stop_active_arm("cancel_requested")
                worker.join(timeout=1.0)
                if stop_result["success"]:
                    goal_handle.canceled()
                    return self._arm_result(result, False, "SKILL_CANCELLED", "arm action cancelled", stop_result)
                goal_handle.abort()
                return self._arm_result(result, False, stop_result["error_code"], stop_result["message"], stop_result)

            if elapsed >= timeout_s:
                stop_result = self._stop_active_arm("arm_action_timeout")
                worker.join(timeout=1.0)
                goal_handle.abort()
                return self._arm_result(
                    result,
                    False,
                    "ARM_ACTION_TIMEOUT",
                    f"arm action timed out after {timeout_s}s",
                    {"stop_result": stop_result, **self._backend_metadata(action_spec)},
                )
            time.sleep(0.2)

        worker.join(timeout=0.0)
        elapsed = time.monotonic() - started
        if errors:
            goal_handle.abort()
            return self._arm_result(
                result,
                False,
                "ARM_ACTION_BACKEND_ERROR",
                errors[0],
                self._backend_metadata(action_spec),
            )
        goal_handle.succeed()
        return self._arm_result(
            result,
            True,
            "",
            "",
            {"status": "finished", "duration_s": round(elapsed, 3), **self._backend_metadata(action_spec)},
        )

    def set_gripper(self, request: SetGripper.Request, response: SetGripper.Response):
        command = str(request.command or "").strip()
        force = str(request.force or "low").strip() or "low"
        action_name = self._canonical_gripper_action(command, force)
        action_spec = self._allowed_gripper_actions().get(action_name)
        if action_spec is None:
            response.success = False
            response.error_code = "GRIPPER_COMMAND_NOT_ALLOWED"
            response.reason = f"gripper command is not allowlisted: command={command}, force={force}"
            response.result_json = "{}"
            return response
        if self._gripper_pub.get_subscription_count() <= 0:
            response.success = False
            response.error_code = "BACKEND_UNAVAILABLE"
            response.reason = f"gripper backend unavailable: no subscribers on {self._gripper_topic()}"
            response.result_json = json.dumps({"topic": self._gripper_topic()}, ensure_ascii=False)
            return response

        pulse = int(action_spec.get("pulse", 0))
        limits = dict(self._gripper_profile().get("limits") or {})
        min_pulse = int(limits.get("min_pulse", 0))
        max_pulse = int(limits.get("max_pulse", 1000))
        if pulse < min_pulse or pulse > max_pulse:
            response.success = False
            response.error_code = "GRIPPER_RANGE_INVALID"
            response.reason = f"configured pulse {pulse} outside [{min_pulse}, {max_pulse}]"
            response.result_json = "{}"
            return response

        duration_s = float(self._gripper_profile().get("duration_s", 0.6))
        msg = ServosPosition()
        msg.duration = duration_s
        msg.position_unit = str(self._gripper_profile().get("position_unit") or "pulse")
        servo = ServoPosition()
        servo.id = int(self._gripper_profile().get("servo_id", 10))
        servo.position = float(pulse)
        msg.position = [servo]
        self._gripper_pub.publish(msg)
        self._last_gripper_command = action_name
        result = {
            "action": action_name,
            "command": action_spec.get("command"),
            "force": action_spec.get("force", force),
            "topic": self._gripper_topic(),
            "servo_id": servo.id,
            "pulse": pulse,
            "duration_s": duration_s,
        }
        response.success = True
        response.error_code = ""
        response.reason = ""
        response.result_json = json.dumps(result, ensure_ascii=False)
        return response

    def stop_arm(self, request: StopRobot.Request, response: StopRobot.Response):
        stop_result = self._stop_active_arm(str(request.reason or "stop_requested"))
        response.success = bool(stop_result["success"])
        response.error_code = str(stop_result["error_code"])
        response.message = json.dumps(stop_result, ensure_ascii=False)
        return response

    def _arm_result(self, result: MoveArmNamed.Result, success: bool, error_code: str, reason: str, data: dict[str, Any]):
        result.success = bool(success)
        result.error_code = str(error_code)
        result.reason = str(reason)
        result.result_json = json.dumps(data, ensure_ascii=False)
        return result

    def _allowed_named_actions(self) -> dict[str, dict[str, Any]]:
        actions = {}
        for name, spec in dict(self._arm_profile().get("allowed_named_actions") or {}).items():
            action_name = str(name)
            action_spec = dict(spec or {})
            action_spec["name"] = action_name
            actions[action_name] = action_spec
        return actions

    def _allowed_gripper_actions(self) -> dict[str, dict[str, Any]]:
        return {str(name): dict(spec or {}) for name, spec in dict(self._gripper_profile().get("allowed_commands") or {}).items()}

    def _canonical_action_name(self, name: str) -> str:
        aliases = {
            "home": "arm_home",
            "init": "arm_home",
            "camera_up": "camera_pitch_up_15",
            "arm_home": "arm_home",
        }
        return aliases.get(name.strip(), name.strip())

    def _canonical_gripper_action(self, command: str, force: str) -> str:
        stripped = command.strip()
        if stripped in self._allowed_gripper_actions():
            return stripped
        if stripped == "open":
            return "open_gripper"
        if stripped == "close" and force == "low":
            return "close_gripper_low_force"
        return stripped

    def _arm_backend_available(self) -> bool:
        if self._uses_direct_action_group():
            return (
                self._ensure_direct_action_controller() is not None
                and self._gripper_pub.get_subscription_count() > 0
            )
        return (
            self._arm_command_pub is not None
            and self._arm_command_pub.get_subscription_count() > 0
            and self._status_client is not None
            and self._status_client.wait_for_service(timeout_sec=0.1)
        )

    def _stop_backend_available(self) -> bool:
        if self._uses_direct_action_group():
            return self._ensure_direct_action_controller() is not None
        stop_backend = dict(self._arm_profile().get("stop_backend") or {})
        return str(stop_backend.get("type") or "none") not in {"", "none"}

    def _stop_active_arm(self, reason: str) -> dict[str, Any]:
        with self._lock:
            active_action = self._active_action
            active_backend_action = self._active_backend_action
        if not active_action:
            return {"success": True, "error_code": "", "message": "no active arm action", "reason": reason}
        if self._uses_direct_action_group():
            controller = self._ensure_direct_action_controller()
            if controller is None:
                return {
                    "success": False,
                    "error_code": "STOP_BACKEND_UNAVAILABLE",
                    "message": "servo action group controller is unavailable",
                    "reason": reason,
                    "active_action": active_action,
                    "active_backend_action": active_backend_action,
                }
            controller.stop_action_group()
            return {
                "success": True,
                "error_code": "",
                "message": "stop requested through ActionGroupController",
                "reason": reason,
                "active_action": active_action,
                "active_backend_action": active_backend_action,
            }
        stop_backend = dict(self._arm_profile().get("stop_backend") or {})
        backend_type = str(stop_backend.get("type") or "none")
        if backend_type == "none":
            return {
                "success": False,
                "error_code": "STOP_BACKEND_UNAVAILABLE",
                "message": str(stop_backend.get("reason") or "no configured arm stop backend"),
                "reason": reason,
                "active_action": active_action,
                "active_backend_action": active_backend_action,
                "stop_backend": stop_backend,
            }
        return {
            "success": False,
            "error_code": "STOP_BACKEND_UNIMPLEMENTED",
            "message": f"configured arm stop backend is not implemented: {backend_type}",
            "reason": reason,
            "stop_backend": stop_backend,
        }

    def _read_arm_status(self, timeout_s: float = 0.5) -> str:
        if self._status_client is None or not self._status_client.wait_for_service(timeout_sec=0.1):
            return "status_unavailable"
        future = self._status_client.call_async(Trigger.Request())
        started = time.monotonic()
        while not future.done() and time.monotonic() - started < timeout_s:
            time.sleep(0.02)
        if not future.done():
            return "status_timeout"
        response = future.result()
        if response is None or not bool(response.success):
            return "status_error"
        return str(response.message or "").strip().lower() or "unknown"

    def _backend_metadata(self, action_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "profile_name": self._profile.get("profile_name", ""),
            "backend": action_spec.get("backend", self._arm_profile().get("backend_type", "")),
            "action_name": action_spec.get("name", ""),
            "backend_type": self._arm_backend_type(),
            "backend_action": action_spec.get("backend_action", ""),
            "command_topic": self._arm_command_topic(),
            "status_service": self._arm_status_service(),
            "action_group_path": self._action_group_path(),
            "action_file": str(self._action_group_file(str(action_spec.get("backend_action", "")))),
        }

    def _backend_unavailable_reason(self, action_spec: dict[str, Any]) -> str:
        if self._uses_direct_action_group():
            if ActionGroupController is None:
                return "servo action group controller import failed"
            if self._gripper_pub.get_subscription_count() <= 0:
                return f"arm backend unavailable: no subscribers on {self._gripper_topic()}"
            return "arm direct action group backend unavailable"
        return f"arm backend unavailable: topic {self._arm_command_topic()} or service {self._arm_status_service()} missing"

    def _action_group_path(self) -> str:
        return str(self._arm_profile().get("action_group_path") or "/home/ubuntu/software/arm_pc/ActionGroups")

    def _action_group_file(self, action_name: str) -> Path:
        return Path(self._action_group_path()) / f"{action_name}.d6a"

    def _action_files_available(self) -> dict[str, bool]:
        return {
            name: self._action_group_file(str(spec.get("backend_action", name))).exists()
            for name, spec in self._allowed_named_actions().items()
        }

    def _camera_pose_actions_available(self) -> dict[str, bool]:
        return {
            name: self._action_group_file(str(spec.get("backend_action", name))).exists()
            for name, spec in self._allowed_named_actions().items()
            if name.startswith("camera_")
        }

    def _missing_backend_error_code(self, action_name: str) -> str:
        return "CAMERA_POSE_BACKEND_MISSING" if action_name.startswith("camera_") else "ARM_ACTION_BACKEND_MISSING"

    def _ensure_direct_action_controller(self):
        if ActionGroupController is None:
            return None
        with self._direct_action_lock:
            if self._direct_action_controller is None:
                self._direct_action_controller = ActionGroupController(self._gripper_pub, self._action_group_path())
            return self._direct_action_controller


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ManipulationBridgeNode()
    executor = MultiThreadedExecutor(num_threads=4)
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
