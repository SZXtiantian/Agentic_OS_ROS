#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${AGENTIC_GRIPPER_MOTION_LOG_DIR:-/tmp/agentic_gripper_minimal_motion_$(date +%Y%m%d_%H%M%S)}"
REPORT_PATH="${AGENTIC_GRIPPER_MOTION_REPORT:-$LOG_DIR/gripper_minimal_motion.json}"
ALLOW_ARM="${AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION:-0}"
SERVO_ID=10
POSITIONS=(500 540 500)
DURATION_S="${AGENTIC_GRIPPER_MOTION_DURATION_S:-0.8}"
TOLERANCE="${AGENTIC_GRIPPER_POSITION_TOLERANCE:-25}"
RRC_PID=""
STARTED_RRC=0

log() {
  printf '\n[%s] %s\n' "$(date -Is)" "$*"
}

source_ros() {
  set +u
  source /opt/ros/humble/setup.bash
  if [[ -f /home/ubuntu/ros2_ws/install/setup.bash ]]; then
    source /home/ubuntu/ros2_ws/install/setup.bash
  fi
  set -u
}

cleanup() {
  if [[ "$STARTED_RRC" == "1" ]] && [[ -n "$RRC_PID" ]] && kill -0 "$RRC_PID" >/dev/null 2>&1; then
    kill "$RRC_PID" >/dev/null 2>&1 || true
    wait "$RRC_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_for_service() {
  local service_name="$1"
  for _ in {1..50}; do
    if timeout 5 ros2 service list --no-daemon 2>/dev/null | grep -Fxq "$service_name"; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

service_active() {
  timeout 5 ros2 service list --no-daemon 2>/dev/null | grep -Fxq "$1"
}

start_controller_owner() {
  source_ros
  mkdir -p "$LOG_DIR/raw"
  if service_active "/ros_robot_controller/bus_servo/get_state"; then
    return 0
  fi
  log "starting ros_robot_controller for gripper minimal motion"
  ros2 run ros_robot_controller ros_robot_controller > "$LOG_DIR/ros_robot_controller.log" 2>&1 &
  RRC_PID="$!"
  STARTED_RRC=1
  wait_for_service "/ros_robot_controller/bus_servo/get_state"
}

read_gripper() {
  local label="$1"
  source_ros
  timeout 12 ros2 service call /ros_robot_controller/bus_servo/get_state \
    ros_robot_controller_msgs/srv/GetBusServoState \
    "{cmd: [{id: $SERVO_ID, get_id: 1, get_position: 1, get_voltage: 1, get_temperature: 1, get_torque_state: 1}]}" \
    > "$LOG_DIR/raw/${label}.txt" 2>&1 || true
}

command_gripper() {
  local label="$1"
  local position="$2"
  source_ros
  timeout 8 ros2 topic pub --once /ros_robot_controller/bus_servo/set_position \
    ros_robot_controller_msgs/msg/ServosPosition \
    "{duration: $DURATION_S, position: [{id: $SERVO_ID, position: $position}]}" \
    > "$LOG_DIR/raw/command_${label}.txt" 2>&1 || true
  sleep 1
}

write_report() {
  python3 - "$LOG_DIR" "$REPORT_PATH" "$SERVO_ID" "$TOLERANCE" "${POSITIONS[@]}" <<'PY'
import json
import re
import sys
from pathlib import Path

log_dir = Path(sys.argv[1])
report_path = Path(sys.argv[2])
servo_id = int(sys.argv[3])
tolerance = int(sys.argv[4])
commands = [int(item) for item in sys.argv[5:]]


def parse_values(text: str, field: str):
    match = re.search(rf"{field}=\[([^\]]*)\]", text)
    if not match:
        return None
    body = match.group(1).strip()
    if not body:
        return []
    return [int(part.strip()) for part in body.split(",") if part.strip()]


def one(values):
    if values is None or len(values) != 1:
        return None
    return values[0]


def parse_state(label: str):
    path = log_dir / "raw" / f"{label}.txt"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return {
        "raw_path": str(path),
        "present_id": parse_values(text, "present_id"),
        "position": parse_values(text, "position"),
        "vin_mv": parse_values(text, "voltage"),
        "temperature_c": parse_values(text, "temperature"),
        "torque_state": parse_values(text, "enable_torque"),
    }


states = {"before": parse_state("before")}
step_results = []
for index, command in enumerate(commands, start=1):
    label = f"after_{index}_{command}"
    state = parse_state(label)
    actual = one(state["position"])
    ok = actual is not None and abs(actual - command) <= tolerance
    step_results.append(
        {
            "label": label,
            "command_position": command,
            "actual_position": actual,
            "within_tolerance": ok,
            "state": state,
        }
    )
states["steps"] = step_results

positions = [item["actual_position"] for item in step_results if item["actual_position"] is not None]
movement_span = max(positions) - min(positions) if positions else 0
errors = []
if not all(item["within_tolerance"] for item in step_results):
    errors.append("GRIPPER_POSITION_READBACK_MISMATCH")
if movement_span < 20:
    errors.append("ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED")

report = {
    "schema_version": "1.0",
    "success": not errors,
    "error_codes": errors,
    "reason": "" if not errors else "gripper minimal motion was not confirmed by readback",
    "servo_id": servo_id,
    "commands": commands,
    "tolerance": tolerance,
    "movement_span": movement_span,
    "states": states,
    "log_dir": str(log_dir),
    "report_path": str(report_path),
}
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(0 if report["success"] else 1)
PY
}

main() {
  if [[ "$ALLOW_ARM" != "1" ]]; then
    printf '{"success":false,"error_code":"ARM_MOTION_DISABLED","reason":"set AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 to run gripper minimal motion"}\n'
    exit 1
  fi
  if [[ "${AGENTIC_ARM_TORQUE_STATE_VERIFIED:-0}" != "1" ]] || [[ -z "${AGENTIC_ARM_EXPECTED_TORQUE_STATE:-}" ]]; then
    printf '{"success":false,"error_code":"ARM_TORQUE_DISABLED_OR_UNVERIFIED","reason":"run health gate with verified torque semantics before motion"}\n'
    exit 1
  fi
  log "AgenticOS gripper minimal motion"
  log "log_dir=$LOG_DIR"
  mkdir -p "$LOG_DIR/raw"
  start_controller_owner
  read_gripper "before"
  index=1
  for position in "${POSITIONS[@]}"; do
    command_gripper "${index}_${position}" "$position"
    read_gripper "after_${index}_${position}"
    index=$((index + 1))
  done
  write_report
}

main "$@"
