import json
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import rclpy
import yaml
from agentic_msgs.action import MoveArmNamed, PickColorBlock, PlaceColorBlock
from agentic_msgs.srv import GetArmState, SetGripper, StopRobot
from kinematics.kinematics_control import set_pose_target
from kinematics_msgs.srv import GetRobotPose, SetRobotPose
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
        self._pick_server = ActionServer(
            self,
            PickColorBlock,
            "/agentic/manipulation/pick_color_block",
            execute_callback=self.execute_pick_color_block,
            goal_callback=self.pick_goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self._callback_group,
        )
        self._place_server = ActionServer(
            self,
            PlaceColorBlock,
            "/agentic/manipulation/place_color_block",
            execute_callback=self.execute_place_color_block,
            goal_callback=self.place_goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self._callback_group,
        )
        self._current_pose_client = self.create_client(GetRobotPose, self._get_current_pose_service(), callback_group=self._callback_group)
        self._set_pose_client = self.create_client(SetRobotPose, self._set_pose_target_service(), callback_group=self._callback_group)
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

    def _color_block_profile(self) -> dict[str, Any]:
        return dict(self._profile.get("color_block") or {})

    def _get_current_pose_service(self) -> str:
        return str(self._arm_profile().get("get_current_pose_service") or "/kinematics/get_current_pose")

    def _set_pose_target_service(self) -> str:
        return str(self._arm_profile().get("kinematics_pose_service") or self._arm_profile().get("set_pose_target_service") or "/kinematics/set_pose_target")

    def goal_callback(self, goal_request):
        name = self._canonical_action_name(str(goal_request.name))
        if name not in self._allowed_named_actions():
            self.get_logger().warning(f"rejecting non-allowlisted arm action: {goal_request.name}")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def pick_goal_callback(self, goal_request):
        color = str(goal_request.color or "").strip().lower()
        if color not in {"red", "green", "blue", "yellow"}:
            self.get_logger().warning(f"rejecting pick for unsupported color: {goal_request.color}")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def place_goal_callback(self, goal_request):
        target = str(goal_request.place_target or "").strip()
        if not target:
            self.get_logger().warning("rejecting place goal without place_target")
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

    def execute_pick_color_block(self, goal_handle):
        result = PickColorBlock.Result()
        request = goal_handle.request
        timeout_s = int(request.timeout_s or 60)
        started = time.monotonic()
        color = str(request.color or "").strip().lower()
        try:
            detection = json.loads(str(request.detection_json or "{}"))
        except json.JSONDecodeError:
            goal_handle.abort()
            return self._pick_result(result, False, "COLOR_BLOCK_DETECTION_INVALID", "detection_json is not valid JSON", {})
        if not isinstance(detection, dict) or not detection:
            goal_handle.abort()
            return self._pick_result(result, False, "COLOR_BLOCK_DETECTION_INVALID", "detection_json is required", {})
        if str(detection.get("color") or "").lower() != color:
            goal_handle.abort()
            return self._pick_result(result, False, "COLOR_BLOCK_DETECTION_INVALID", "detection color does not match pick color", {"detection": detection})
        camera_position = detection.get("camera_position_m")
        if not isinstance(camera_position, list) or len(camera_position) < 3:
            goal_handle.abort()
            return self._pick_result(result, False, "COLOR_BLOCK_DETECTION_INVALID", "detection lacks camera_position_m", {"detection": detection})
        ready = self._color_block_motion_ready()
        if not ready["success"]:
            goal_handle.abort()
            return self._pick_result(result, False, str(ready["error_code"]), str(ready["reason"]), ready)

        with self._lock:
            if self._active_action:
                goal_handle.abort()
                return self._pick_result(result, False, "ARM_BUSY", f"active action: {self._active_action}", {})
            self._active_action = "pick_color_block"
            self._active_backend_action = "pick_color_block"

        try:
            plan = self._plan_color_block_pick([float(v) for v in camera_position[:3]], timeout_s=timeout_s)
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return self._pick_result(result, False, "SKILL_CANCELLED", "pick cancelled before execution", {})
            self._publish_pick_feedback(goal_handle, "planned", 0.2, {"plan": plan})
            self._execute_pick_motion(goal_handle, plan, timeout_s=timeout_s)
            duration_s = round(time.monotonic() - started, 3)
            payload = {
                "color": color,
                "target": str(request.target or "workspace"),
                "detection": detection,
                "arm_position_m": plan["pick_position_m"],
                "pregrasp_position_m": plan.get("pregrasp_position_m"),
                "lift_position_m": plan["lift_position_m"],
                "pregrasp_pulse": plan.get("pregrasp_pulse"),
                "pick_pulse": plan["pick_pulse"],
                "lift_pulse": plan["lift_pulse"],
                "pick_pitch": plan["pick_pitch"],
                "execution_strategy": plan.get("execution_strategy", "ik_color_block_pick"),
                "motion_sequence": plan.get("fixed_pick_sequence", []),
                "held": False,
                "held_verified": False,
                "held_claim_source": "post_pick_vision_verification_required",
                "motion_completed": True,
                "duration_s": duration_s,
                "bridge_action": "/agentic/manipulation/pick_color_block",
            }
            goal_handle.succeed()
            return self._pick_result(result, True, "", "", payload)
        except Exception as exc:
            self._stop_active_arm("pick_color_block_error")
            goal_handle.abort()
            return self._pick_result(
                result,
                False,
                "COLOR_BLOCK_PICK_FAILED",
                str(exc),
                {"active_action": "pick_color_block"},
            )
        finally:
            with self._lock:
                self._active_action = ""
                self._active_backend_action = ""

    def execute_place_color_block(self, goal_handle):
        result = PlaceColorBlock.Result()
        request = goal_handle.request
        target = str(request.place_target or "").strip() or "hold_position"
        timeout_s = int(request.timeout_s or 60)
        started = time.monotonic()
        try:
            pick_result = json.loads(str(request.pick_result_json or "{}"))
        except json.JSONDecodeError:
            goal_handle.abort()
            return self._place_result(result, False, "COLOR_BLOCK_PICK_RESULT_INVALID", "pick_result_json is not valid JSON", {})
        if target in {"hold_position", "held", "lifted", "keep_holding"}:
            goal_handle.succeed()
            return self._place_result(
                result,
                True,
                "",
                "",
                {
                    "place_target": target,
                    "held": True,
                    "released": False,
                    "pick_result": pick_result,
                    "bridge_action": "/agentic/manipulation/place_color_block",
                },
            )
        ready = self._color_block_motion_ready(check_kinematics=False)
        if not ready["success"]:
            goal_handle.abort()
            return self._place_result(result, False, str(ready["error_code"]), str(ready["reason"]), ready)
        with self._lock:
            if self._active_action:
                goal_handle.abort()
                return self._place_result(result, False, "ARM_BUSY", f"active action: {self._active_action}", {})
            self._active_action = "place_color_block"
            self._active_backend_action = "place_color_block"
        try:
            self._execute_place_motion(goal_handle, pick_result, timeout_s=timeout_s)
            duration_s = round(time.monotonic() - started, 3)
            payload = {
                "color": str(request.color or ""),
                "place_target": target,
                "held": False,
                "released": True,
                "pick_result": pick_result,
                "duration_s": duration_s,
                "bridge_action": "/agentic/manipulation/place_color_block",
            }
            goal_handle.succeed()
            return self._place_result(result, True, "", "", payload)
        except Exception as exc:
            self._stop_active_arm("place_color_block_error")
            goal_handle.abort()
            return self._place_result(result, False, "COLOR_BLOCK_PLACE_FAILED", str(exc), {"place_target": target})
        finally:
            with self._lock:
                self._active_action = ""
                self._active_backend_action = ""

    def _color_block_motion_ready(self, *, check_kinematics: bool = True) -> dict[str, Any]:
        if self._gripper_pub.get_subscription_count() <= 0:
            return {
                "success": False,
                "error_code": "MANIPULATION_BACKEND_UNAVAILABLE",
                "reason": f"no subscribers on {self._gripper_topic()}",
            }
        if check_kinematics:
            if not self._current_pose_client.wait_for_service(timeout_sec=0.2):
                return {
                    "success": False,
                    "error_code": "MANIPULATION_BACKEND_UNAVAILABLE",
                    "reason": f"kinematics service unavailable: {self._get_current_pose_service()}",
                }
            if not self._set_pose_client.wait_for_service(timeout_sec=0.2):
                return {
                    "success": False,
                    "error_code": "MANIPULATION_BACKEND_UNAVAILABLE",
                    "reason": f"kinematics service unavailable: {self._set_pose_target_service()}",
                }
        return {"success": True}

    def _plan_color_block_pick(self, camera_position_m: list[float], *, timeout_s: int) -> dict[str, Any]:
        deadline = time.monotonic() + max(1, timeout_s)
        endpoint_matrix = self._current_endpoint_matrix(deadline)
        arm_position = self._camera_to_arm_position(camera_position_m, endpoint_matrix)
        cfg = self._color_block_profile()
        arm_position = [
            arm_position[0] + float(cfg.get("pick_x_offset_m", 0.0)),
            arm_position[1] + float(cfg.get("pick_y_offset_m", 0.0)),
            arm_position[2] + float(cfg.get("pick_z_offset_m", 0.0)),
        ]
        bounds = dict(self._arm_profile().get("workspace_bounds_m") or {})
        self._check_workspace_bounds(arm_position, bounds)
        pitch = float(cfg.get("pick_pitch_near", 80.0)) if arm_position[2] < float(cfg.get("near_z_threshold_m", 0.20)) else float(cfg.get("pick_pitch_far", 30.0))
        pick_pulse = self._solve_ik(arm_position, pitch, deadline)
        pregrasp_position = list(arm_position)
        pregrasp_position[2] += float(cfg.get("pregrasp_height_m", 0.06))
        pregrasp_pulse = self._solve_ik(pregrasp_position, pitch, deadline)
        lift_position = list(arm_position)
        lift_position[2] += float(cfg.get("lift_height_m", 0.10))
        lift_pulse = self._solve_ik(lift_position, pitch, deadline)
        plan = {
            "pick_position_m": [round(float(value), 5) for value in arm_position],
            "pregrasp_position_m": [round(float(value), 5) for value in pregrasp_position],
            "lift_position_m": [round(float(value), 5) for value in lift_position],
            "pick_pitch": pitch,
            "pick_pulse": pick_pulse,
            "pregrasp_pulse": pregrasp_pulse,
            "lift_pulse": lift_pulse,
        }
        fixed_sequence = self._fixed_pick_sequence(cfg)
        if fixed_sequence:
            plan["execution_strategy"] = str(cfg.get("pick_execution_strategy") or "aligned_fixed_pulse_sequence")
            plan["fixed_pick_sequence"] = fixed_sequence
        return plan

    def _execute_pick_motion(self, goal_handle, plan: dict[str, Any], *, timeout_s: int) -> None:
        del timeout_s
        cfg = self._color_block_profile()
        fixed_sequence = list(plan.get("fixed_pick_sequence") or [])
        if fixed_sequence:
            self._execute_fixed_pick_sequence(goal_handle, fixed_sequence)
            return
        gripper_open = int(cfg.get("gripper_open", dict(self._gripper_profile().get("limits") or {}).get("open_pulse", 760)))
        gripper_close = int(cfg.get("gripper_close", dict(self._gripper_profile().get("limits") or {}).get("close_low_force_pulse", 520)))
        pregrasp = list(plan["pregrasp_pulse"])
        pick = list(plan["pick_pulse"])
        lift = list(plan["lift_pulse"])
        self._publish_pick_feedback(goal_handle, "opening_gripper", 0.3, {})
        self._publish_servos(0.6, [(10, gripper_open)])
        self._sleep_or_cancel(goal_handle, 0.7)
        self._publish_pick_feedback(goal_handle, "aligning_base", 0.38, {"base_pulse": pregrasp[0]})
        self._publish_servos(0.8, [(1, pregrasp[0]), (10, gripper_open)])
        self._sleep_or_cancel(goal_handle, 0.9)
        self._publish_pick_feedback(goal_handle, "moving_pregrasp", 0.45, {"pregrasp_pulse": pregrasp})
        self._publish_servos(1.3, [(1, pregrasp[0]), (2, pregrasp[1]), (3, pregrasp[2]), (4, pregrasp[3]), (5, pregrasp[4]), (10, gripper_open)])
        self._sleep_or_cancel(goal_handle, 1.4)
        pick_move_duration_s = float(cfg.get("pick_move_duration_s", 1.0))
        pick_settle_s = float(cfg.get("pick_settle_s", pick_move_duration_s + 0.2))
        self._publish_pick_feedback(
            goal_handle,
            "moving_pick",
            0.6,
            {"pick_pulse": pick, "duration_s": pick_move_duration_s, "settle_s": pick_settle_s},
        )
        self._publish_servos(
            pick_move_duration_s,
            [(1, pick[0]), (2, pick[1]), (3, pick[2]), (4, pick[3]), (5, pick[4]), (10, gripper_open)],
        )
        self._sleep_or_cancel(goal_handle, pick_settle_s)
        self._publish_pick_feedback(goal_handle, "closing_gripper", 0.75, {})
        self._publish_servos(0.8, [(10, gripper_close)])
        self._sleep_or_cancel(goal_handle, 1.4)
        self._publish_pick_feedback(goal_handle, "lifting", 0.9, {"lift_pulse": lift})
        self._publish_servos(1.0, [(1, lift[0]), (2, lift[1]), (3, lift[2]), (4, lift[3]), (5, lift[4]), (10, gripper_close)])
        self._sleep_or_cancel(goal_handle, 1.0)

    def _fixed_pick_sequence(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        if str(cfg.get("pick_execution_strategy") or "").strip() != "aligned_fixed_pulse_sequence":
            return []
        sequence: list[dict[str, Any]] = []
        for index, item in enumerate(list(cfg.get("fixed_pick_sequence") or [])):
            if not isinstance(item, dict):
                raise RuntimeError(f"fixed_pick_sequence step {index + 1} must be an object")
            positions: list[list[int]] = []
            for pair in list(item.get("positions") or []):
                values = list(pair or [])
                if len(values) < 2:
                    raise RuntimeError(f"fixed_pick_sequence step {index + 1} has an invalid servo pair")
                positions.append([int(values[0]), int(values[1])])
            if not positions:
                raise RuntimeError(f"fixed_pick_sequence step {index + 1} has no servo positions")
            sequence.append(
                {
                    "status": str(item.get("status") or f"fixed_pick_step_{index + 1}"),
                    "progress": float(item.get("progress", min(0.95, 0.3 + index / 4.0))),
                    "duration_s": float(item.get("duration_s", 1.0)),
                    "settle_s": float(item.get("settle_s", float(item.get("duration_s", 1.0)) + 0.1)),
                    "positions": positions,
                }
            )
        return sequence

    def _execute_fixed_pick_sequence(self, goal_handle, sequence: list[dict[str, Any]]) -> None:
        for index, item in enumerate(sequence):
            if goal_handle.is_cancel_requested:
                raise RuntimeError("pick cancelled")
            positions = [(int(pair[0]), int(pair[1])) for pair in list(item.get("positions") or [])]
            duration_s = float(item.get("duration_s", 1.0))
            settle_s = float(item.get("settle_s", duration_s + 0.1))
            self._publish_pick_feedback(
                goal_handle,
                str(item.get("status") or f"fixed_pick_step_{index + 1}"),
                float(item.get("progress", min(0.95, 0.3 + index / max(len(sequence), 1)))),
                {"duration_s": duration_s, "settle_s": settle_s, "positions": positions},
            )
            self._publish_servos(duration_s, positions)
            self._sleep_or_cancel(goal_handle, settle_s)

    def _execute_place_motion(self, goal_handle, pick_result: dict[str, Any], *, timeout_s: int) -> None:
        del timeout_s, pick_result
        cfg = self._color_block_profile()
        gripper_open = int(cfg.get("gripper_open", dict(self._gripper_profile().get("limits") or {}).get("open_pulse", 760)))
        gripper_close = int(cfg.get("gripper_close", dict(self._gripper_profile().get("limits") or {}).get("close_low_force_pulse", 520)))
        sequence = list(cfg.get("place_sequence") or [])
        if not sequence:
            sequence = [
                {"duration_s": 1.5, "positions": [[1, 500], [2, 535], [3, 170], [4, 220], [5, 500], [10, gripper_close]]},
                {"duration_s": 1.5, "positions": [[1, 500], [2, 160], [3, 400], [4, 350], [5, 500], [10, gripper_close]]},
                {"duration_s": 1.0, "positions": [[10, gripper_open]]},
                {"duration_s": 1.0, "positions": [[1, 500], [2, 667], [3, 21], [4, 188], [5, 500], [10, gripper_open]]},
            ]
        for index, item in enumerate(sequence):
            if goal_handle.is_cancel_requested:
                raise RuntimeError("place cancelled")
            self._publish_place_feedback(goal_handle, f"place_step_{index + 1}", min(0.95, 0.2 + index / max(len(sequence), 1)), item)
            positions = [(int(pair[0]), int(pair[1])) for pair in list(item.get("positions") or [])]
            self._publish_servos(float(item.get("duration_s", 1.0)), positions)
            self._sleep_or_cancel(goal_handle, float(item.get("duration_s", 1.0)) + 0.1)

    def _current_endpoint_matrix(self, deadline: float) -> np.ndarray:
        response = self._call_service(self._current_pose_client, GetRobotPose.Request(), deadline)
        if response is None or not bool(response.success) or not bool(response.solution):
            raise RuntimeError("current endpoint pose unavailable")
        return self._pose_to_matrix(response.pose)

    def _solve_ik(self, position_m: list[float], pitch: float, deadline: float) -> list[int]:
        cfg = self._color_block_profile()
        request = set_pose_target(
            position_m,
            pitch,
            [float(cfg.get("pitch_range_min", -180.0)), float(cfg.get("pitch_range_max", 180.0))],
            float(cfg.get("pitch_resolution", 1.0)),
        )
        response = self._call_service(self._set_pose_client, request, deadline)
        pulse = [int(value) for value in list(getattr(response, "pulse", []) or [])]
        if response is None or not bool(response.success) or len(pulse) < 5:
            raise RuntimeError(f"IK failed for position={position_m} pitch={pitch}")
        return pulse[:5]

    def _call_service(self, client, request, deadline: float):
        future = client.call_async(request)
        while time.monotonic() < deadline:
            if future.done():
                return future.result()
            time.sleep(0.02)
        raise TimeoutError("service call timed out")

    def _camera_to_arm_position(self, camera_position_m: list[float], endpoint_matrix: np.ndarray) -> list[float]:
        cfg = self._color_block_profile()
        hand2cam = self._hand2cam_matrix(
            float(cfg.get("hand2cam_tx_m", -0.101)),
            float(cfg.get("hand2cam_ty_m", 0.0)),
            float(cfg.get("hand2cam_tz_m", 0.037)),
        )
        camera_translation = np.eye(4, dtype=float)
        camera_translation[:3, 3] = np.asarray(camera_position_m[:3], dtype=float)
        arm_pose = endpoint_matrix @ hand2cam @ camera_translation
        return [float(value) for value in arm_pose[:3, 3]]

    def _publish_servos(self, duration_s: float, positions: list[tuple[int, int]]) -> None:
        self._validate_servo_positions(positions)
        msg = ServosPosition()
        msg.duration = float(duration_s)
        msg.position_unit = str(self._gripper_profile().get("position_unit") or "pulse")
        msg.position = []
        for servo_id, pulse in positions:
            servo = ServoPosition()
            servo.id = int(servo_id)
            servo.position = float(pulse)
            msg.position.append(servo)
        self._gripper_pub.publish(msg)

    def _validate_servo_positions(self, positions: list[tuple[int, int]]) -> None:
        limits = dict(self._arm_profile().get("joint_pulse_limits") or {})
        gripper_limits = dict(self._gripper_profile().get("limits") or {})
        for servo_id, pulse in positions:
            if int(servo_id) == 10:
                min_pulse = int(gripper_limits.get("min_pulse", 0))
                max_pulse = int(gripper_limits.get("max_pulse", 1000))
            else:
                min_pulse, max_pulse = [int(v) for v in list(limits.get(f"joint{servo_id}") or limits.get("joint1") or [0, 1000])[:2]]
            if int(pulse) < min_pulse or int(pulse) > max_pulse:
                raise RuntimeError(f"servo {servo_id} pulse {pulse} outside [{min_pulse}, {max_pulse}]")

    def _check_workspace_bounds(self, position_m: list[float], bounds: dict[str, Any]) -> None:
        if not bounds:
            return
        for axis, value in zip(("x", "y", "z"), position_m):
            raw = bounds.get(axis)
            if not isinstance(raw, list) or len(raw) < 2:
                continue
            low, high = float(raw[0]), float(raw[1])
            if float(value) < low or float(value) > high:
                raise RuntimeError(f"planned {axis}={value:.3f} outside workspace bounds [{low:.3f}, {high:.3f}]")

    def _sleep_or_cancel(self, goal_handle, duration_s: float) -> None:
        deadline = time.monotonic() + max(0.0, duration_s)
        while time.monotonic() < deadline:
            if goal_handle.is_cancel_requested:
                raise RuntimeError("motion cancelled")
            time.sleep(min(0.05, deadline - time.monotonic()))

    def _publish_pick_feedback(self, goal_handle, status: str, progress: float, data: dict[str, Any]) -> None:
        feedback = PickColorBlock.Feedback()
        feedback.status = status
        feedback.progress = float(progress)
        feedback.feedback_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        goal_handle.publish_feedback(feedback)

    def _publish_place_feedback(self, goal_handle, status: str, progress: float, data: dict[str, Any]) -> None:
        feedback = PlaceColorBlock.Feedback()
        feedback.status = status
        feedback.progress = float(progress)
        feedback.feedback_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        goal_handle.publish_feedback(feedback)

    def _pick_result(self, result: PickColorBlock.Result, success: bool, error_code: str, reason: str, data: dict[str, Any]):
        result.success = bool(success)
        result.error_code = str(error_code)
        result.reason = str(reason)
        result.result_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return result

    def _place_result(self, result: PlaceColorBlock.Result, success: bool, error_code: str, reason: str, data: dict[str, Any]):
        result.success = bool(success)
        result.error_code = str(error_code)
        result.reason = str(reason)
        result.result_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return result

    def _pose_to_matrix(self, pose) -> np.ndarray:
        mat = np.eye(4, dtype=float)
        mat[:3, :3] = self._quaternion_to_matrix(
            float(pose.orientation.x),
            float(pose.orientation.y),
            float(pose.orientation.z),
            float(pose.orientation.w),
        )
        mat[:3, 3] = [float(pose.position.x), float(pose.position.y), float(pose.position.z)]
        return mat

    def _quaternion_to_matrix(self, x: float, y: float, z: float, w: float) -> np.ndarray:
        norm = x * x + y * y + z * z + w * w
        if norm == 0.0:
            return np.eye(3, dtype=float)
        scale = 2.0 / norm
        xx, yy, zz = x * x * scale, y * y * scale, z * z * scale
        xy, xz, yz = x * y * scale, x * z * scale, y * z * scale
        wx, wy, wz = w * x * scale, w * y * scale, w * z * scale
        return np.array(
            [
                [1.0 - yy - zz, xy - wz, xz + wy],
                [xy + wz, 1.0 - xx - zz, yz - wx],
                [xz - wy, yz + wx, 1.0 - xx - yy],
            ],
            dtype=float,
        )

    def _hand2cam_matrix(self, tx: float, ty: float, tz: float) -> np.ndarray:
        return np.array(
            [
                [0.0, 0.0, 1.0, tx],
                [-1.0, 0.0, 0.0, ty],
                [0.0, -1.0, 0.0, tz],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
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
