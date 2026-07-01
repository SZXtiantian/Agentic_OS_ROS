#!/usr/bin/env bash
set -euo pipefail

if [[ "${AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION:-0}" != "1" ]]; then
  printf '{"success":false,"error_code":"ARM_MOTION_DISABLED","reason":"set AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 to run real action group probe"}\n'
  exit 1
fi

LOG_DIR="${AGENTIC_ARM_ACTION_GROUP_PROBE_LOG_DIR:-/tmp/agentic_action_group_probe_$(date +%Y%m%d_%H%M%S)}"
REPORT_PATH="${AGENTIC_ARM_ACTION_GROUP_PROBE_REPORT:-$LOG_DIR/action_group_probe.json}"
PROFILE="${ROBOT_PROFILE_FILE:-/tmp/agentic_arm_action_group_probe_profile.yaml}"
RECOVERY_ACTION="${AGENTIC_ARM_ACTION_GROUP_PROBE_RECOVERY:-probe_init}"
MOTION_DELTA_MIN="${AGENTIC_ARM_ACTION_GROUP_PROBE_MIN_DELTA:-20}"

set +u
source /opt/ros/humble/setup.bash
if [[ -f /home/ubuntu/ros2_ws/install/setup.bash ]]; then
  source /home/ubuntu/ros2_ws/install/setup.bash
fi
if [[ -f /home/ubuntu/agentic_ws/install/system_skill_nodes/setup.bash ]]; then
  source /home/ubuntu/agentic_ws/install/system_skill_nodes/setup.bash
fi
set -u

mkdir -p "$LOG_DIR/raw"

python3 - "$LOG_DIR" "$REPORT_PATH" "$PROFILE" "$RECOVERY_ACTION" "$MOTION_DELTA_MIN" <<'PY'
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

log_dir = Path(sys.argv[1])
report_path = Path(sys.argv[2])
profile = sys.argv[3]
recovery_action = sys.argv[4]
motion_delta_min = int(sys.argv[5])
raw_dir = log_dir / "raw"
servo_ids = [1, 2, 3, 4, 5, 10]

default_actions = [
    ("probe_horizontal", "horizontal", 8),
    ("probe_camera_up", "camera_up", 8),
    ("probe_detect_left", "detect_left", 8),
    ("probe_detect_right", "detect_right", 8),
    ("probe_left_up", "left_up", 8),
    ("probe_left_down", "left_down", 8),
    ("probe_right_up", "right_up", 8),
    ("probe_right_down", "right_down", 8),
]


def configured_actions() -> list[tuple[str, str, int]]:
    text = os.environ.get("AGENTIC_ARM_ACTION_GROUP_PROBE_ACTIONS", "").strip()
    if not text:
        return default_actions
    actions: list[tuple[str, str, int]] = []
    for part in text.split(","):
        items = [item.strip() for item in part.split(":")]
        if len(items) == 2:
            actions.append((items[0], items[1], 8))
        elif len(items) == 3:
            actions.append((items[0], items[1], int(items[2])))
        else:
            raise SystemExit(f"invalid AGENTIC_ARM_ACTION_GROUP_PROBE_ACTIONS entry: {part}")
    return actions


def run(cmd: list[str], timeout: int = 15) -> dict[str, object]:
    def output_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return {"returncode": proc.returncode, "output": proc.stdout}
    except subprocess.TimeoutExpired as exc:
        return {"returncode": 124, "output": output_text(exc.stdout) + "\nCOMMAND_TIMEOUT"}


def parse_values(text: str, field: str) -> list[int] | None:
    match = re.search(rf"{field}=\[([^\]]*)\]", text)
    if not match:
        return None
    body = match.group(1).strip()
    if not body:
        return []
    values: list[int] = []
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            return None
    return values


def one(values: list[int] | None) -> int | None:
    if values is None or len(values) != 1:
        return None
    return values[0]


def read_state(label: str) -> dict[str, dict[str, object]]:
    states: dict[str, dict[str, object]] = {}
    for servo_id in servo_ids:
        command = [
            "ros2",
            "service",
            "call",
            "/ros_robot_controller/bus_servo/get_state",
            "ros_robot_controller_msgs/srv/GetBusServoState",
            (
                "{cmd: [{id: "
                f"{servo_id}"
                ", get_id: 1, get_position: 1, get_voltage: 1, "
                "get_temperature: 1, get_torque_state: 1}]}"
            ),
        ]
        result = run(command, timeout=12)
        raw_path = raw_dir / f"{label}_id_{servo_id}.txt"
        raw_path.write_text(str(result["output"]), encoding="utf-8", errors="replace")
        text = str(result["output"])
        states[str(servo_id)] = {
            "returncode": result["returncode"],
            "raw_path": str(raw_path),
            "present_id": parse_values(text, "present_id"),
            "position": parse_values(text, "position"),
            "vin_mv": parse_values(text, "voltage"),
            "temperature_c": parse_values(text, "temperature"),
            "torque_state": parse_values(text, "enable_torque"),
        }
    return states


def positions(states: dict[str, dict[str, object]]) -> dict[str, int | None]:
    return {servo_id: one(state.get("position")) for servo_id, state in states.items()}  # type: ignore[arg-type]


def deltas(before: dict[str, dict[str, object]], after: dict[str, dict[str, object]]) -> dict[str, int | None]:
    before_positions = positions(before)
    after_positions = positions(after)
    result: dict[str, int | None] = {}
    for servo_id in sorted(before_positions, key=lambda item: int(item)):
        before_value = before_positions[servo_id]
        after_value = after_positions.get(servo_id)
        result[servo_id] = None if before_value is None or after_value is None else abs(after_value - before_value)
    return result


def backend_alive() -> dict[str, bool]:
    services = str(run(["ros2", "service", "list"], timeout=8)["output"])
    actions = str(run(["ros2", "action", "list"], timeout=8)["output"])
    return {
        "bus_servo_get_state": "/ros_robot_controller/bus_servo/get_state" in services,
        "agentic_arm_get_state": "/agentic/arm/get_state" in services,
        "arm_move_named": "/agentic/arm/move_named" in actions,
    }


def send_action(name: str, request_id: str, timeout_s: int) -> dict[str, object]:
    goal = f"{{name: {name}, request_id: {request_id}, timeout_s: {timeout_s}}}"
    command = [
        "ros2",
        "action",
        "send_goal",
        "/agentic/arm/move_named",
        "agentic_msgs/action/MoveArmNamed",
        goal,
        "--feedback",
    ]
    result = run(command, timeout=timeout_s + 12)
    output = str(result["output"])
    raw_path = raw_dir / f"{request_id}.txt"
    raw_path.write_text(output, encoding="utf-8", errors="replace")
    output_lower = output.lower()
    success_text = "success=true" in output_lower or "success: true" in output_lower
    code_match = re.search(r"error_code(?:=|:)\s*'([^']*)'", output)
    reason_match = re.search(r"reason(?:=|:)\s*'([^']*)'", output)
    return {
        "command": " ".join(command),
        "returncode": result["returncode"],
        "success": result["returncode"] == 0 and "Goal accepted" in output and success_text,
        "error_code": code_match.group(1) if code_match else "",
        "reason": reason_match.group(1) if reason_match else "",
        "raw_output_path": str(raw_path),
        "raw_output_excerpt": output[-1200:],
    }


actions = configured_actions()
report: dict[str, object] = {
    "schema_version": "1.0",
    "profile": profile,
    "log_dir": str(log_dir),
    "report_path": str(report_path),
    "motion_delta_min": motion_delta_min,
    "recovery_action": recovery_action,
    "backend_alive_initial": backend_alive(),
    "actions": [],
    "error_codes": [],
}
errors: list[dict[str, str]] = []

for index, (name, backend_action, timeout_s) in enumerate(actions, start=1):
    print(f"ACTION {index}/{len(actions)} {backend_action}", flush=True)
    action_report: dict[str, object] = {
        "name": name,
        "backend_action": backend_action,
        "timeout_s": timeout_s,
    }
    before = read_state(f"{backend_action}_before")
    action_report["before"] = before
    move = send_action(name, f"probe_{backend_action}_{int(time.time())}", timeout_s)
    action_report["move_result"] = move
    after = read_state(f"{backend_action}_after")
    action_report["after"] = after
    position_delta = deltas(before, after)
    max_delta = max([value for value in position_delta.values() if isinstance(value, int)] or [0])
    action_report["position_delta"] = position_delta
    action_report["max_position_delta"] = max_delta
    action_report["physical_motion_confirmed_by_position"] = bool(move["success"] and max_delta >= motion_delta_min)
    action_report["backend_alive_after_move"] = backend_alive()
    if not action_report["physical_motion_confirmed_by_position"]:
        errors.append({"backend_action": backend_action, "error_code": "ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED"})

    recovery = send_action(recovery_action, f"probe_recovery_after_{backend_action}_{int(time.time())}", 8)
    recovery_after = read_state(f"{backend_action}_recovery_after")
    recovery_delta = deltas(after, recovery_after)
    action_report["recovery"] = {
        "command_name": recovery_action,
        "backend_action": "init",
        "result": recovery,
        "after": recovery_after,
        "position_delta": recovery_delta,
        "max_position_delta": max([value for value in recovery_delta.values() if isinstance(value, int)] or [0]),
        "backend_alive_after_recovery": backend_alive(),
    }
    if not recovery["success"]:
        errors.append({"backend_action": backend_action, "error_code": "ARM_RECOVERY_FAILED"})
    report["actions"].append(action_report)  # type: ignore[index]
    report["error_codes"] = errors
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

report["backend_alive_final"] = backend_alive()
report["error_codes"] = errors
report["success"] = not errors
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps({"success": report["success"], "report_path": str(report_path), "error_codes": errors}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["success"] else 1)
PY
