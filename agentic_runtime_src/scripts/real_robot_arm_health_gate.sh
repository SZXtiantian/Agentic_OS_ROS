#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${AGENTIC_ARM_HEALTH_LOG_DIR:-/tmp/agentic_arm_health_gate_$(date +%Y%m%d_%H%M%S)}"
REPORT_PATH="${AGENTIC_ARM_HEALTH_REPORT:-$LOG_DIR/arm_health_gate.json}"
STOP_APP_NODE="${AGENTIC_ARM_HEALTH_STOP_APP:-1}"
STOP_BUTTON_SCAN="${AGENTIC_ARM_HEALTH_STOP_BUTTON_SCAN:-1}"
SERIAL_DEVICE="${AGENTIC_ARM_SERIAL_DEVICE:-/dev/ttyACM0}"
TORQUE_VERIFIED="${AGENTIC_ARM_TORQUE_STATE_VERIFIED:-0}"
EXPECTED_TORQUE_STATE="${AGENTIC_ARM_EXPECTED_TORQUE_STATE:-}"
VIN_MIN_MV="${AGENTIC_ARM_VIN_MIN_MV:-9000}"
VIN_MAX_MV="${AGENTIC_ARM_VIN_MAX_MV:-12600}"
SERVO_IDS=(1 2 3 4 5 10)
RRC_PID=""
SERVO_PID=""
STARTED_RRC=0
STARTED_SERVO=0

log() {
  printf '\n[%s] %s\n' "$(date -Is)" "$*"
}

json_event() {
  local status="$1"
  local code="$2"
  local detail="$3"
  printf '{"status":"%s","code":"%s","detail":"%s"}\n' "$status" "$code" "$detail"
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
  if [[ "$STARTED_SERVO" == "1" ]] && [[ -n "$SERVO_PID" ]] && kill -0 "$SERVO_PID" >/dev/null 2>&1; then
    kill "$SERVO_PID" >/dev/null 2>&1 || true
    wait "$SERVO_PID" >/dev/null 2>&1 || true
  fi
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

stop_app_service_if_needed() {
  if systemctl is-active --quiet start_app_node.service; then
    if [[ "$STOP_APP_NODE" != "1" ]]; then
      json_event "failed" "START_APP_NODE_ACTIVE" "start_app_node.service is active; set AGENTIC_ARM_HEALTH_STOP_APP=1 or stop it manually"
      return 1
    fi
    log "stopping start_app_node.service for single serial owner mode"
    if sudo -n true >/dev/null 2>&1; then
      sudo systemctl stop start_app_node.service
    else
      json_event "failed" "SUDO_REQUIRED" "sudo is required to stop start_app_node.service"
      return 1
    fi
  fi
}

serial_owner_pids() {
  if [[ ! -e "$SERIAL_DEVICE" ]] || ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  lsof -t "$SERIAL_DEVICE" 2>/dev/null | sort -n | uniq || true
}

serial_owner_snapshot() {
  local label="$1"
  mkdir -p "$LOG_DIR"
  {
    echo "label=$label"
    echo "serial_device=$SERIAL_DEVICE"
    if [[ -e "$SERIAL_DEVICE" ]]; then
      ls -l "$SERIAL_DEVICE" || true
      if command -v lsof >/dev/null 2>&1; then
        lsof "$SERIAL_DEVICE" 2>/dev/null || true
      fi
    else
      echo "serial_device_missing=true"
    fi
  } > "$LOG_DIR/serial_owners_${label}.txt"
}

stop_button_scan_if_needed() {
  if systemctl is-active --quiet button_scan.service; then
    if [[ "$STOP_BUTTON_SCAN" != "1" ]]; then
      json_event "failed" "BUTTON_SCAN_SERIAL_OWNER_ACTIVE" "button_scan.service is active and may own $SERIAL_DEVICE"
      return 1
    fi
    log "stopping button_scan.service for single serial owner mode"
    if sudo -n true >/dev/null 2>&1; then
      sudo systemctl stop button_scan.service
    else
      json_event "failed" "SUDO_REQUIRED" "sudo is required to stop button_scan.service"
      return 1
    fi
  fi
}

fail_if_unexpected_serial_owners() {
  local phase="$1"
  serial_owner_snapshot "$phase"
  local pids
  pids="$(serial_owner_pids | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  local unexpected=()
  local pid
  for pid in $pids; do
    local cmd
    cmd="$(ps -p "$pid" -o cmd= 2>/dev/null || true)"
    if [[ "$cmd" == *"ros_robot_controller"* ]]; then
      continue
    fi
    unexpected+=("$pid:$cmd")
  done
  if [[ "${#unexpected[@]}" -gt 0 ]]; then
    json_event "failed" "ARM_SERIAL_PORT_MULTI_OWNER" "${unexpected[*]}"
    return 1
  fi
}

start_minimal_stack() {
  source_ros
  mkdir -p "$LOG_DIR"

  if service_active "/ros_robot_controller/bus_servo/get_state"; then
    json_event "ok" "ROS_ROBOT_CONTROLLER_ALREADY_RUNNING" "/ros_robot_controller/bus_servo/get_state"
  else
    log "starting ros_robot_controller minimal stack owner"
    ros2 run ros_robot_controller ros_robot_controller > "$LOG_DIR/ros_robot_controller.log" 2>&1 &
    RRC_PID="$!"
    STARTED_RRC=1
    wait_for_service "/ros_robot_controller/bus_servo/get_state" || {
      json_event "failed" "ROS_ROBOT_CONTROLLER_UNAVAILABLE" "service /ros_robot_controller/bus_servo/get_state did not appear; see $LOG_DIR/ros_robot_controller.log"
      return 1
    }
  fi

  if service_active "/controller_manager/init_finish"; then
    json_event "ok" "SERVO_CONTROLLER_ALREADY_RUNNING" "/controller_manager/init_finish"
  else
    log "starting servo_controller minimal stack"
    ros2 run servo_controller servo_controller --ros-args \
      --params-file /home/ubuntu/ros2_ws/src/driver/servo_controller/config/servo_controller.yaml \
      -p base_frame:=base_footprint > "$LOG_DIR/servo_controller.log" 2>&1 &
    SERVO_PID="$!"
    STARTED_SERVO=1
    wait_for_service "/controller_manager/init_finish" || {
      json_event "failed" "SERVO_CONTROLLER_UNAVAILABLE" "service /controller_manager/init_finish did not appear; see $LOG_DIR/servo_controller.log"
      return 1
    }
  fi

  timeout 8 ros2 service call /ros_robot_controller/init_finish std_srvs/srv/Trigger "{}" \
    > "$LOG_DIR/ros_robot_controller_init_finish.txt" 2>&1 || true
  timeout 8 ros2 service call /controller_manager/init_finish std_srvs/srv/Trigger "{}" \
    > "$LOG_DIR/controller_manager_init_finish.txt" 2>&1 || true
}

read_servo_state() {
  source_ros
  mkdir -p "$LOG_DIR/raw"
  for servo_id in "${SERVO_IDS[@]}"; do
    log "reading bus servo id=$servo_id"
    timeout 12 ros2 service call /ros_robot_controller/bus_servo/get_state \
      ros_robot_controller_msgs/srv/GetBusServoState \
      "{cmd: [{id: $servo_id, get_id: 1, get_position: 1, get_offset: 1, get_voltage: 1, get_temperature: 1, get_position_limit: 1, get_voltage_limit: 1, get_max_temperature_limit: 1, get_torque_state: 1}]}" \
      > "$LOG_DIR/raw/id_${servo_id}.txt" 2>&1 || true
  done
}

write_report() {
  python3 - "$LOG_DIR" "$REPORT_PATH" "$VIN_MIN_MV" "$VIN_MAX_MV" "$TORQUE_VERIFIED" "$EXPECTED_TORQUE_STATE" "${SERVO_IDS[@]}" <<'PY'
import json
import re
import sys
from pathlib import Path

log_dir = Path(sys.argv[1])
report_path = Path(sys.argv[2])
vin_min_mv = int(sys.argv[3])
vin_max_mv = int(sys.argv[4])
torque_verified = sys.argv[5] == "1"
expected_torque_text = sys.argv[6]
expected_torque = int(expected_torque_text) if expected_torque_text in {"0", "1"} else None
servo_ids = [int(item) for item in sys.argv[7:]]


def parse_values(text: str, field: str):
    match = re.search(rf"{field}=\[([^\]]*)\]", text)
    if not match:
        return None
    body = match.group(1).strip()
    if not body:
        return []
    values = []
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            return None
    return values


def one(values):
    if values is None or len(values) != 1:
        return None
    return values[0]


servos = {}
errors = []

for servo_id in servo_ids:
    raw_path = log_dir / "raw" / f"id_{servo_id}.txt"
    text = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
    item = {
        "raw_path": str(raw_path),
        "present_id": parse_values(text, "present_id"),
        "position": parse_values(text, "position"),
        "offset": parse_values(text, "offset"),
        "vin_mv": parse_values(text, "voltage"),
        "temperature_c": parse_values(text, "temperature"),
        "position_limit": parse_values(text, "position_limit"),
        "voltage_limit_mv": parse_values(text, "voltage_limit"),
        "max_temperature_limit_c": parse_values(text, "max_temperature_limit"),
        "torque_state": parse_values(text, "enable_torque"),
    }
    servos[str(servo_id)] = item

    present = one(item["present_id"])
    if present != servo_id:
        errors.append("ARM_SERVO_ID_MISSING")

    position = one(item["position"])
    if position is None or position < 0 or position > 1000:
        errors.append("ARM_SERVO_ID3_POSITION_INVALID" if servo_id == 3 else "ARM_SERVO_POSITION_INVALID")

    vin = one(item["vin_mv"])
    if vin is None:
        errors.append("ARM_POWER_READBACK_MISSING")
    elif vin < vin_min_mv:
        errors.append("ARM_POWER_UNDERVOLTAGE")
    elif vin > vin_max_mv:
        errors.append("ARM_POWER_OVERVOLTAGE")

    torque = one(item["torque_state"])
    if torque is None or torque not in {0, 1}:
        errors.append("ARM_TORQUE_STATE_UNREADABLE")
    elif torque_verified and expected_torque is not None and torque != expected_torque:
        errors.append("ARM_TORQUE_DISABLED_OR_UNVERIFIED")

if not torque_verified or expected_torque is None:
    errors.append("ARM_TORQUE_DISABLED_OR_UNVERIFIED")

unique_errors = []
for code in errors:
    if code not in unique_errors:
        unique_errors.append(code)

primary_errors = [code for code in unique_errors if code != "ARM_HEALTH_GATE_FAILED"]
if unique_errors:
    unique_errors.append("ARM_HEALTH_GATE_FAILED")

blocked_motion_tests = []
if "ARM_HEALTH_GATE_FAILED" in unique_errors:
    blocked_motion_tests = [
        "gripper_10_500_540_500",
        "camera_up",
        "horizontal",
        "detect_left",
        "detect_right",
        "left_up",
        "left_down",
        "right_up",
        "right_down",
        "agenticos_arm_move_named",
        "real_multi_angle_capture",
    ]

if primary_errors == ["ARM_TORQUE_DISABLED_OR_UNVERIFIED"]:
    next_allowed_stage = "torque_semantics_required"
elif unique_errors:
    next_allowed_stage = "hardware_repair_required"
else:
    next_allowed_stage = "gripper_minimal_motion"

report = {
    "schema_version": "1.0",
    "success": not unique_errors,
    "error_codes": unique_errors,
    "reason": "" if not unique_errors else "arm health gate failed; do not send motion commands",
    "next_allowed_stage": next_allowed_stage,
    "blocked_motion_tests": blocked_motion_tests,
    "thresholds": {
        "vin_min_mv": vin_min_mv,
        "vin_max_mv": vin_max_mv,
        "position_min": 0,
        "position_max": 1000,
        "torque_state_verified": torque_verified,
        "expected_torque_state": expected_torque,
    },
    "servo_ids": servo_ids,
    "servos": servos,
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
  log "AgenticOS real robot arm health gate"
  log "log_dir=$LOG_DIR"
  stop_app_service_if_needed
  serial_owner_snapshot "before_button_scan_stop"
  stop_button_scan_if_needed
  fail_if_unexpected_serial_owners "after_button_scan_stop"
  start_minimal_stack
  fail_if_unexpected_serial_owners "after_minimal_stack_start"
  read_servo_state
  write_report
}

main "$@"
