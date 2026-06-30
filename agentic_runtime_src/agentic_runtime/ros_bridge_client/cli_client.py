from __future__ import annotations

import asyncio
import ast
import json
import math
import os
import re
import shutil
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_runtime.provider_contracts import ros_bridge_contract
from agentic_runtime.types import new_id

CommandRunner = Callable[[list[str], int], Awaitable[str]]


class RosBridgeCommandError(RuntimeError):
    def __init__(self, error_code: str, reason: str) -> None:
        super().__init__(reason)
        self.error_code = error_code
        self.reason = reason


class Ros2CliBridgeClient:
    """Non-rclpy runtime client for Agentic-owned ROS2 bridge interfaces.

    This client intentionally shells out to the ROS2 CLI so runtime code keeps
    the same architectural boundary as an OS userland service: no ROS2 Python
    imports, no direct topic/action objects, and no vendor driver imports.
    """

    def __init__(self, timeout_s: int = 10, runner: CommandRunner | None = None) -> None:
        self.timeout_s = timeout_s
        self.runner = runner or self._run_command
        self._last_status: dict[str, Any] = {
            "operation": "",
            "command": [],
            "success": False,
            "error_code": "",
            "reason": "",
            "updated_at": "",
        }

    def status(self) -> dict[str, Any]:
        contract = ros_bridge_contract("cli")
        return {
            "state": "ready" if shutil.which("ros2") else "unavailable",
            "provider": "ros2_cli",
            "validate_config": contract["validate_config"],
            "health": contract["health"],
            "capabilities": contract["capabilities"],
            "error_code": contract["error_code"],
            "missing": contract["missing"],
            "details": contract["details"],
            "implemented_modes": contract["implemented_modes"],
            "available_modes": contract["available_modes"],
            "unsupported_modes": contract["unsupported_modes"],
            "reserved_modes": contract["reserved_modes"],
            "ros2_cli_available": shutil.which("ros2") is not None,
            "last_operation": str(self._last_status.get("operation") or ""),
            "last_command": list(self._last_status.get("command") or []),
            "last_success": bool(self._last_status.get("success", False)),
            "last_error": {
                "error_code": str(self._last_status.get("error_code") or ""),
                "reason": str(self._last_status.get("reason") or ""),
                "operation": str(self._last_status.get("operation") or ""),
            },
            "updated_at": str(self._last_status.get("updated_at") or ""),
        }

    async def resolve_place(self, name: str) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/world/resolve_place",
                "agentic_msgs/srv/ResolvePlace",
                {"name": name},
            )
            data = _parse_required_response(output)
            success = self._finalize_response("resolve_place", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("resolve_place", exc)
            return _bridge_error(exc, place=_normalize_place({}, fallback_name=name))
        place = _normalize_place(data.get("place") or {}, fallback_name=name)
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "place": place,
        }

    async def get_robot_state(self) -> dict[str, Any]:
        try:
            output = await self._service_call("/agentic/robot/get_state", "agentic_msgs/srv/GetRobotState", {})
            data = _parse_required_response(output)
            success = self._finalize_response("get_robot_state", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("get_robot_state", exc)
            return _bridge_error(exc, state={})
        state = _normalize_state(data.get("state") or {})
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "state": state,
        }

    async def check_safety(self, skill_name: str, args: dict[str, Any], app_id: str) -> dict[str, Any]:
        payload = {"skill_name": skill_name, "args_json": json.dumps(args, ensure_ascii=False), "app_id": app_id}
        timeout_s = max(self.timeout_s, 20)
        try:
            output = await self._service_call("/agentic/safety/check", "agentic_msgs/srv/CheckSafety", payload, timeout_s)
        except (TimeoutError, RosBridgeCommandError) as exc:
            if isinstance(exc, RosBridgeCommandError) and exc.error_code != "ROS_SERVICE_UNAVAILABLE":
                return {"allowed": False, "error_code": exc.error_code, "reason": exc.reason}
            await asyncio.sleep(0.5)
            try:
                output = await self._service_call("/agentic/safety/check", "agentic_msgs/srv/CheckSafety", payload, timeout_s)
            except (TimeoutError, RosBridgeCommandError) as exc:
                if isinstance(exc, RosBridgeCommandError) and exc.error_code != "ROS_SERVICE_UNAVAILABLE":
                    return {"allowed": False, "error_code": exc.error_code, "reason": exc.reason}
                return {"allowed": False, "error_code": "SAFETY_BACKEND_TIMEOUT", "reason": str(exc)}
        except RuntimeError as exc:
            return {"allowed": False, "error_code": "SAFETY_BACKEND_UNAVAILABLE", "reason": str(exc)}
        try:
            data = _parse_required_response(output)
            allowed = self._finalize_response("check_safety", data, "allowed", default_failure_code="SAFETY_REJECTED")
        except RosBridgeCommandError as exc:
            self._record_error("check_safety", exc)
            return {"allowed": False, "error_code": exc.error_code, "reason": exc.reason}
        return {
            "allowed": allowed,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
        }

    async def navigate_to(self, place: str, timeout_s: int, cancel_event=None) -> dict[str, Any]:
        if cancel_event is not None and cancel_event.is_set():
            return {"success": False, "error_code": "SKILL_CANCELLED", "reason": "navigation cancelled before dispatch"}
        try:
            output = await self._action_send_goal(
                "/agentic/robot/navigate_to_place",
                "agentic_msgs/action/NavigateToPlace",
                {"place": place, "request_id": new_id("nav"), "timeout_s": int(timeout_s)},
                timeout_s,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("navigate_to", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("navigate_to", exc)
            return _bridge_error(exc, result={})
        result_json = _decode_json_field(data.get("result_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "result": result_json,
        }

    async def inspect_area(self, place: str, timeout_s: int, request_id: str = "") -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/perception/inspect_area",
                "agentic_msgs/srv/InspectArea",
                {"place": place, "request_id": request_id or new_id("inspect"), "timeout_s": int(timeout_s)},
                timeout_s + 5,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("inspect_area", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("inspect_area", exc)
            return _bridge_error(exc, summary="", objects=[], anomalies=[], evidence_path="", evidence={})
        result_json = _decode_json_field(data.get("result_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "summary": str(data.get("summary") or result_json.get("summary", "")),
            "objects": list(data.get("objects") or result_json.get("objects", [])),
            "anomalies": list(data.get("anomalies") or result_json.get("anomalies", [])),
            "evidence_path": str(result_json.get("evidence_path", "")),
            "evidence": dict(result_json.get("evidence", {})),
        }

    async def observe(self, target: str, timeout_s: int) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/perception/observe",
                "agentic_msgs/srv/Observe",
                {"target": target, "request_id": new_id("observe"), "timeout_s": int(timeout_s)},
                timeout_s + 5,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("observe", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("observe", exc)
            return _bridge_error(exc, summary="", objects=[], evidence_path="", evidence={})
        evidence = _decode_json_field(data.get("evidence_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", data.get("summary", ""))),
            "summary": str(data.get("summary", "")),
            "objects": list(data.get("objects") or []),
            "evidence_path": str(data.get("evidence_path", "")),
            "evidence": evidence,
        }

    async def capture_photo(self, target: str, label: str, timeout_s: int) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/perception/capture_photo",
                "agentic_msgs/srv/CapturePhoto",
                {"target": target, "label": label, "request_id": new_id("capture"), "timeout_s": int(timeout_s)},
                timeout_s + 5,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("capture_photo", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("capture_photo", exc)
            return _bridge_error(exc, image_path="", metadata_path="", evidence={})
        evidence = _decode_json_field(data.get("evidence_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "image_path": str(data.get("image_path", "")),
            "metadata_path": str(data.get("metadata_path", "")),
            "evidence": evidence,
        }

    async def detect_color_block(self, color: str, target: str, evidence_label: str, timeout_s: int) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/perception/detect_color_block",
                "agentic_msgs/srv/DetectColorBlock",
                {
                    "color": color,
                    "target": target,
                    "evidence_label": evidence_label,
                    "request_id": new_id("detect_block"),
                    "timeout_s": int(timeout_s),
                },
                timeout_s + 5,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("detect_color_block", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("detect_color_block", exc)
            return _bridge_error(exc, detection={}, evidence={})
        detection = _decode_json_field(data.get("detection_json"))
        evidence = _decode_json_field(data.get("evidence_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "detection": detection,
            "evidence": evidence,
        }

    async def center_color_block(self, color: str, target: str, evidence_label: str, timeout_s: int) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/perception/center_color_block",
                "agentic_msgs/srv/CenterColorBlock",
                {
                    "color": color,
                    "target": target,
                    "evidence_label": evidence_label,
                    "request_id": new_id("center_block"),
                    "timeout_s": int(timeout_s),
                },
                timeout_s + 5,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("center_color_block", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("center_color_block", exc)
            return _bridge_error(exc, alignment={}, evidence={})
        alignment = _decode_json_field(data.get("alignment_json"))
        evidence = _decode_json_field(data.get("evidence_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "alignment": alignment,
            "evidence": evidence,
        }

    async def verify_held_color_block(
        self,
        color: str,
        target: str,
        detection: dict[str, Any],
        pick_result: dict[str, Any],
        evidence_label: str,
        timeout_s: int,
    ) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/perception/verify_held_color_block",
                "agentic_msgs/srv/VerifyHeldColorBlock",
                {
                    "color": color,
                    "target": target,
                    "detection_json": json.dumps(detection, ensure_ascii=False, sort_keys=True),
                    "pick_result_json": json.dumps(pick_result, ensure_ascii=False, sort_keys=True),
                    "evidence_label": evidence_label,
                    "request_id": new_id("verify_held"),
                    "timeout_s": int(timeout_s),
                },
                timeout_s + 5,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("verify_held_color_block", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("verify_held_color_block", exc)
            return _bridge_error(exc, verified_held=False, verification={}, evidence={})
        verification = _decode_json_field(data.get("verification_json"))
        evidence = _decode_json_field(data.get("evidence_json"))
        return {
            "success": success,
            "verified_held": bool(data.get("verified_held", False)),
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "verification": verification,
            "evidence": evidence,
        }

    async def get_arm_state(self) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/arm/get_state",
                "agentic_msgs/srv/GetArmState",
                {"request_id": new_id("arm_state")},
            )
            data = _parse_required_response(output)
            success = self._finalize_response("get_arm_state", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("get_arm_state", exc)
            return _bridge_error(exc, state=_normalize_arm_state({}))
        state = _normalize_arm_state(data.get("state") or {})
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "state": state,
        }

    async def move_arm_named(self, name: str, timeout_s: int, cancel_event=None) -> dict[str, Any]:
        if cancel_event is not None and cancel_event.is_set():
            return {"success": False, "error_code": "SKILL_CANCELLED", "reason": "arm action cancelled before dispatch"}
        try:
            output = await self._action_send_goal(
                "/agentic/arm/move_named",
                "agentic_msgs/action/MoveArmNamed",
                {"name": name, "request_id": new_id("arm"), "timeout_s": int(timeout_s)},
                timeout_s + 2,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("move_arm_named", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("move_arm_named", exc)
            return _bridge_error(exc, result={})
        result_json = _decode_json_field(data.get("result_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "result": result_json,
        }

    async def set_gripper(
        self,
        command: str,
        force: str = "low",
        percentage: float | None = None,
        timeout_s: int = 5,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "command": command,
            "force": force,
            "percentage": float(percentage) if percentage is not None else 0.0,
            "request_id": new_id("gripper"),
            "timeout_s": int(timeout_s),
        }
        try:
            output = await self._service_call("/agentic/gripper/set", "agentic_msgs/srv/SetGripper", payload, timeout_s + 1)
            data = _parse_required_response(output)
            success = self._finalize_response("set_gripper", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("set_gripper", exc)
            return _bridge_error(exc, result={})
        result_json = _decode_json_field(data.get("result_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "result": result_json,
        }

    async def pick_color_block(
        self,
        color: str,
        target: str,
        detection: dict[str, Any],
        evidence: dict[str, Any],
        timeout_s: int,
    ) -> dict[str, Any]:
        try:
            output = await self._action_send_goal(
                "/agentic/manipulation/pick_color_block",
                "agentic_msgs/action/PickColorBlock",
                {
                    "color": color,
                    "target": target,
                    "detection_json": json.dumps(detection, ensure_ascii=False, sort_keys=True),
                    "evidence_json": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                    "request_id": new_id("pick_block"),
                    "timeout_s": int(timeout_s),
                },
                timeout_s + 5,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("pick_color_block", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("pick_color_block", exc)
            return _bridge_error(exc, result={})
        result_json = _decode_json_field(data.get("result_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "result": result_json,
        }

    async def place_color_block(
        self,
        color: str,
        place_target: str,
        pick_result: dict[str, Any],
        timeout_s: int,
    ) -> dict[str, Any]:
        try:
            output = await self._action_send_goal(
                "/agentic/manipulation/place_color_block",
                "agentic_msgs/action/PlaceColorBlock",
                {
                    "color": color,
                    "place_target": place_target,
                    "pick_result_json": json.dumps(pick_result, ensure_ascii=False, sort_keys=True),
                    "request_id": new_id("place_block"),
                    "timeout_s": int(timeout_s),
                },
                timeout_s + 5,
            )
            data = _parse_required_response(output)
            success = self._finalize_response("place_color_block", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("place_color_block", exc)
            return _bridge_error(exc, result={})
        result_json = _decode_json_field(data.get("result_json"))
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "result": result_json,
        }

    async def stop_robot(self, reason: str) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/robot/stop",
                "agentic_msgs/srv/StopRobot",
                {"reason": reason, "request_id": new_id("stop")},
            )
            data = _parse_required_response(output)
            success = self._finalize_response("stop_robot", data, "success")
        except RosBridgeCommandError as exc:
            self._record_error("stop_robot", exc)
            return _bridge_error(exc, message="", reason=reason)
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "message": str(data.get("message", "")),
            "reason": reason,
        }

    async def checkpoint_capability(
        self,
        *,
        skill_name: str,
        args: dict[str, Any],
        app_id: str,
        session_id: str,
        syscall_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "skill_name": skill_name,
            "args_json": json.dumps(args, ensure_ascii=False, sort_keys=True),
            "app_id": app_id,
            "session_id": session_id,
            "syscall_id": syscall_id,
            "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        }
        try:
            output = await self._service_call(
                "/agentic/capability/checkpoint",
                "agentic_msgs/srv/CheckpointCapability",
                payload,
                self.timeout_s,
            )
            data = _parse_required_response(output)
            success = self._finalize_response(
                "checkpoint_capability",
                data,
                "success",
                default_failure_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
            )
        except RosBridgeCommandError as exc:
            self._record_error("checkpoint_capability", exc)
            return _bridge_error(
                exc,
                checkpoint={},
                checkpoint_id="",
                partial_result={},
                completed_coverage=[],
                progress={},
                skill_name=skill_name,
                syscall_id=syscall_id,
            )
        result = _checkpoint_result_from_bridge_data(data)
        if success and not _checkpoint_has_preserved_progress(result):
            reason = "ROS2 bridge checkpoint result did not include preserved progress"
            self._record_operation_result(
                "checkpoint_capability",
                success=False,
                error_code="ROS_RESULT_INVALID",
                reason=reason,
            )
            return {
                "success": False,
                "error_code": "ROS_RESULT_INVALID",
                "reason": reason,
                "checkpoint": {},
                "checkpoint_id": "",
                "partial_result": {},
                "completed_coverage": [],
                "progress": {},
                "skill_name": skill_name,
                "syscall_id": syscall_id,
            }
        return {
            "success": success,
            "error_code": str(data.get("error_code", "")),
            "reason": str(data.get("reason", "")),
            "skill_name": skill_name,
            "syscall_id": syscall_id,
            **result,
        }

    async def ask_human(
        self,
        question: str,
        options=None,
        timeout_s: int = 60,
        require_confirmation: bool = False,
    ) -> dict[str, Any]:
        try:
            output = await self._service_call(
                "/agentic/human/ask",
                "agentic_msgs/srv/AskHuman",
                {
                    "question": question,
                    "options": list(options or []),
                    "timeout_s": int(timeout_s),
                    "require_explicit_confirmation": bool(require_confirmation),
                },
                timeout_s,
            )
            data = _parse_required_response(output)
            answered = self._finalize_response("ask_human", data, "answered", default_failure_code="HUMAN_UNANSWERED")
        except RosBridgeCommandError as exc:
            self._record_error("ask_human", exc)
            return {"success": False, "answered": False, "answer": "", "error_code": exc.error_code, "reason": exc.reason}
        return {
            "success": answered,
            "answered": answered,
            "error_code": "" if answered else str(data.get("error_code") or "HUMAN_UNANSWERED"),
            "answer": str(data.get("answer", "")),
            "reason": str(data.get("reason", "")),
        }

    async def report_say(self, message: str) -> dict[str, Any]:
        path = self._report_log_path()
        record = {
            "created_at": _utc_now(),
            "message": message,
            "transport": "file_report_sink",
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError as exc:
            self._last_status = {
                "operation": "report_say",
                "command": [str(path)],
                "success": False,
                "error_code": "REPORT_BACKEND_UNAVAILABLE",
                "reason": str(exc),
                "updated_at": _utc_now(),
            }
            return {
                "success": False,
                "error_code": "REPORT_BACKEND_UNAVAILABLE",
                "reason": str(exc),
                "report_path": str(path),
            }
        print(message)
        self._last_status = {
            "operation": "report_say",
            "command": [str(path)],
            "success": True,
            "error_code": "",
            "reason": "",
            "updated_at": _utc_now(),
        }
        return {"success": True, "message": message, "transport": "file_report_sink", "report_path": str(path)}

    def _report_log_path(self) -> Path:
        if os.environ.get("AGENTIC_REPORT_LOG"):
            return Path(os.environ["AGENTIC_REPORT_LOG"]).expanduser()
        var_root = Path(os.environ.get("AGENTIC_VAR", "/opt/agentic/var")).expanduser()
        return var_root / "reports" / "report.jsonl"

    async def _service_call(self, name: str, srv_type: str, payload: dict[str, Any], timeout_s: int | None = None) -> str:
        command = ["ros2", "service", "call", name, srv_type, _ros2_payload(payload)]
        self._record_attempt("service_call", command)
        try:
            output = await self.runner(command, int(timeout_s or self.timeout_s))
            self._record_success("service_call", command)
            return output
        except RosBridgeCommandError as exc:
            self._record_error("service_call", exc, command=command)
            raise
        except FileNotFoundError as exc:
            error = RosBridgeCommandError("ROS_BRIDGE_UNAVAILABLE", str(exc) or "ros2 command is unavailable")
            self._record_error("service_call", error, command=command)
            raise error from exc
        except TimeoutError as exc:
            error = RosBridgeCommandError("ROS_SERVICE_UNAVAILABLE", str(exc) or f"ROS2 service timed out: {name}")
            self._record_error("service_call", error, command=command)
            raise error from exc
        except RuntimeError as exc:
            error = RosBridgeCommandError("ROS_SERVICE_UNAVAILABLE", str(exc) or f"ROS2 service unavailable: {name}")
            self._record_error("service_call", error, command=command)
            raise error from exc

    async def _action_send_goal(self, name: str, action_type: str, payload: dict[str, Any], timeout_s: int | None = None) -> str:
        command = ["ros2", "action", "send_goal", name, action_type, _ros2_payload(payload), "--feedback"]
        self._record_attempt("action_send_goal", command)
        try:
            output = await self.runner(command, int(timeout_s or self.timeout_s))
            self._record_success("action_send_goal", command)
            return output
        except RosBridgeCommandError as exc:
            self._record_error("action_send_goal", exc, command=command)
            raise
        except FileNotFoundError as exc:
            error = RosBridgeCommandError("ROS_BRIDGE_UNAVAILABLE", str(exc) or "ros2 command is unavailable")
            self._record_error("action_send_goal", error, command=command)
            raise error from exc
        except TimeoutError as exc:
            error = RosBridgeCommandError("ROS_ACTION_TIMEOUT", str(exc) or f"ROS2 action timed out: {name}")
            self._record_error("action_send_goal", error, command=command)
            raise error from exc
        except RuntimeError as exc:
            error = RosBridgeCommandError("ROS_SERVICE_UNAVAILABLE", str(exc) or f"ROS2 action unavailable: {name}")
            self._record_error("action_send_goal", error, command=command)
            raise error from exc

    def _record_attempt(self, operation: str, command: list[str]) -> None:
        self._last_status = {
            "operation": operation,
            "command": list(command),
            "success": False,
            "error_code": "",
            "reason": "",
            "updated_at": _utc_now(),
        }

    def _record_success(self, operation: str, command: list[str]) -> None:
        self._last_status = {
            "operation": operation,
            "command": list(command),
            "success": True,
            "error_code": "",
            "reason": "",
            "updated_at": _utc_now(),
        }

    def _record_operation_result(
        self,
        operation: str,
        *,
        success: bool,
        error_code: str = "",
        reason: str = "",
    ) -> None:
        previous_command = list(self._last_status.get("command") or [])
        self._last_status = {
            "operation": operation,
            "command": previous_command,
            "success": success,
            "error_code": error_code,
            "reason": reason,
            "updated_at": _utc_now(),
        }

    def _finalize_response(
        self,
        operation: str,
        data: dict[str, Any],
        bool_field: str,
        *,
        default_failure_code: str = "",
    ) -> bool:
        success = _require_bool_response_field(data, bool_field)
        if success:
            self._record_operation_result(operation, success=True)
            return True

        error_code = str(data.get("error_code") or default_failure_code)
        reason = str(data.get("reason") or data.get("message") or "")
        if not error_code:
            error_code = "ROS_RESULT_INVALID"
            reason = reason or f"ROS2 bridge result reported {bool_field}=False without error_code"
        data["error_code"] = error_code
        if reason:
            data["reason"] = reason
        self._record_operation_result(operation, success=False, error_code=error_code, reason=reason)
        return False

    def _record_error(
        self,
        operation: str,
        error: RosBridgeCommandError,
        command: list[str] | None = None,
    ) -> None:
        previous_command = list(self._last_status.get("command") or [])
        self._last_status = {
            "operation": operation,
            "command": list(command or previous_command),
            "success": False,
            "error_code": error.error_code,
            "reason": error.reason,
            "updated_at": _utc_now(),
        }

    async def _run_command(self, command: list[str], timeout_s: int) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RosBridgeCommandError("ROS_BRIDGE_UNAVAILABLE", str(exc) or "ros2 command is unavailable") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"ROS2 bridge command timed out: {' '.join(command)}")
        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="ignore") or f"command failed: {' '.join(command)}")
        return stdout.decode("utf-8", errors="ignore")


def _ros2_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _decode_json_field(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _decode_list_field(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if not value:
        return []
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return list(decoded) if isinstance(decoded, list) else []


def _checkpoint_result_from_bridge_data(data: dict[str, Any]) -> dict[str, Any]:
    checkpoint = _decode_json_field(data.get("checkpoint_json") or data.get("checkpoint"))
    partial_result = _decode_json_field(data.get("partial_result_json") or data.get("partial_result"))
    progress = _decode_json_field(data.get("progress_json") or data.get("progress"))
    completed_coverage = _decode_list_field(data.get("completed_coverage_json") or data.get("completed_coverage"))
    if not partial_result:
        partial_result = _decode_json_field(checkpoint.get("partial_result"))
    if not progress:
        progress = _decode_json_field(checkpoint.get("progress"))
    if not completed_coverage:
        completed_coverage = _decode_list_field(checkpoint.get("completed_coverage"))
    checkpoint_id = str(data.get("checkpoint_id") or checkpoint.get("checkpoint_id") or checkpoint.get("id") or "")
    return {
        "checkpoint": checkpoint,
        "checkpoint_id": checkpoint_id,
        "partial_result": partial_result,
        "completed_coverage": completed_coverage,
        "progress": progress,
    }


def _checkpoint_has_preserved_progress(result: dict[str, Any]) -> bool:
    return bool(
        result.get("checkpoint_id")
        or result.get("partial_result")
        or result.get("completed_coverage")
        or result.get("progress")
        or result.get("checkpoint")
    )


def _parse_response(output: str) -> dict[str, Any]:
    text = output.strip()
    if not text:
        return {}
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return _parse_ros_repr(text)


def _parse_required_response(output: str) -> dict[str, Any]:
    parsed = _parse_response(output)
    if not parsed:
        raise RosBridgeCommandError("ROS_RESULT_INVALID", "ROS2 bridge returned an empty or unparseable result")
    return parsed


def _require_bool_response_field(data: dict[str, Any], field: str) -> bool:
    if field not in data:
        raise RosBridgeCommandError("ROS_RESULT_INVALID", f"ROS2 bridge result missing boolean {field} field")
    value = data[field]
    if not isinstance(value, bool):
        raise RosBridgeCommandError("ROS_RESULT_INVALID", f"ROS2 bridge result field {field} must be boolean")
    return value


def _bridge_error(exc: RosBridgeCommandError, **extra: Any) -> dict[str, Any]:
    return {"success": False, "error_code": exc.error_code, "reason": exc.reason, **extra}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ros_repr(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ["success", "allowed", "answered", "verified_held"]:
        match = re.search(rf"\b{key}\s*[:=]\s*(True|False|true|false)", text)
        if match:
            result[key] = match.group(1).lower() == "true"
    for key in [
        "error_code",
        "reason",
        "message",
        "summary",
        "answer",
        "result_json",
        "detection_json",
        "alignment_json",
        "verification_json",
        "checkpoint_id",
        "checkpoint_json",
        "partial_result_json",
        "completed_coverage_json",
        "progress_json",
        "evidence_path",
        "evidence_json",
        "image_path",
        "metadata_path",
    ]:
        match = re.search(rf"\b{key}\s*[:=]\s*'([^']*)'", text)
        if not match:
            match = re.search(rf'\b{key}\s*[:=]\s*"([^"]*)"', text)
        if match:
            result[key] = match.group(1)
            continue
        match = re.search(rf"\b{key}\s*[:=]\s*([^\n,)]+)", text)
        if match:
            result[key] = match.group(1).strip()
    for key in ["objects", "anomalies", "completed_coverage"]:
        match = re.search(rf"\b{key}\s*[:=]\s*(\[[^\]]*\])", text)
        if match:
            try:
                result[key] = ast.literal_eval(match.group(1))
            except (SyntaxError, ValueError):
                result[key] = []
    place = _parse_place_object(text)
    if place:
        result["place"] = place
    state = _parse_nested_object(
        text,
        "state",
        ["robot_id", "mode", "battery_state", "current_place", "active_task_id", "state_json"],
        bool_fields=["is_localized", "is_moving", "estop_pressed"],
        float_fields=["battery_percent"],
    )
    if state:
        result["state"] = state
    arm_state = _parse_nested_object(
        text,
        "state",
        ["readiness", "active_action", "state_json"],
        bool_fields=["is_moving", "gripper_ready", "stop_available"],
    )
    if arm_state and ("readiness" in arm_state or "gripper_ready" in arm_state or "stop_available" in arm_state):
        result["state"] = arm_state
    return result


def _normalize_place(place: dict[str, Any], fallback_name: str = "") -> dict[str, Any]:
    normalized = dict(place)
    metadata_json = normalized.pop("metadata_json", None)
    if "metadata" not in normalized:
        normalized["metadata"] = _decode_json_field(metadata_json)
    if "name" not in normalized and fallback_name:
        normalized["name"] = fallback_name
    normalized.setdefault("pose", {})
    return normalized


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(state)
    state_json = normalized.pop("state_json", None)
    if "state" not in normalized:
        normalized["state"] = _decode_json_field(state_json)
    normalized.setdefault("pose", {})
    return normalized


def _normalize_arm_state(state: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(state)
    state_json = normalized.pop("state_json", None)
    if "state" not in normalized:
        normalized["state"] = _decode_json_field(state_json)
    normalized.setdefault("readiness", "")
    normalized.setdefault("active_action", "")
    normalized.setdefault("is_moving", False)
    normalized.setdefault("gripper_ready", False)
    normalized.setdefault("stop_available", False)
    return normalized


def _parse_place_object(text: str) -> dict[str, Any]:
    place = _parse_nested_object(text, "place", ["id", "name", "frame_id", "metadata_json"], bool_fields=["allowed"])
    if not place:
        return {}

    position_match = re.search(
        r"position=.*?\bx\s*[:=]\s*(-?\d+(?:\.\d+)?).*?\by\s*[:=]\s*(-?\d+(?:\.\d+)?).*?\bz\s*[:=]\s*(-?\d+(?:\.\d+)?)",
        text,
        flags=re.DOTALL,
    )
    if position_match:
        pose = {
            "x": float(position_match.group(1)),
            "y": float(position_match.group(2)),
            "z": float(position_match.group(3)),
        }
        orientation_match = re.search(
            r"orientation=.*?\bz\s*[:=]\s*(-?\d+(?:\.\d+)?).*?\bw\s*[:=]\s*(-?\d+(?:\.\d+)?)",
            text,
            flags=re.DOTALL,
        )
        if orientation_match:
            pose["yaw"] = 2.0 * math.atan2(float(orientation_match.group(1)), float(orientation_match.group(2)))
        place["pose"] = pose
    return _normalize_place(place)


def _parse_nested_object(
    text: str,
    object_name: str,
    string_fields: list[str],
    bool_fields: list[str] | None = None,
    float_fields: list[str] | None = None,
) -> dict[str, Any]:
    if object_name not in text:
        return {}

    parsed: dict[str, Any] = {}
    for field in string_fields:
        match = re.search(rf"\b{field}\s*[:=]\s*'([^']*)'", text)
        if not match:
            match = re.search(rf'\b{field}\s*[:=]\s*"([^"]*)"', text)
        if match:
            parsed[field] = match.group(1)
    for field in bool_fields or []:
        match = re.search(rf"\b{field}\s*[:=]\s*(True|False|true|false)", text)
        if match:
            parsed[field] = match.group(1).lower() == "true"
    for field in float_fields or []:
        match = re.search(rf"\b{field}\s*[:=]\s*(-?\d+(?:\.\d+)?)", text)
        if match:
            parsed[field] = float(match.group(1))
    return parsed
