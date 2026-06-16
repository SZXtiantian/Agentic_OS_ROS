#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${AGENTIC_TORQUE_PROBE_LOG_DIR:-/tmp/agentic_torque_semantics_probe_$(date +%Y%m%d_%H%M%S)}"
REPORT_PATH="${AGENTIC_TORQUE_PROBE_REPORT:-$LOG_DIR/torque_semantics_probe.json}"
SERVO_ID="${AGENTIC_TORQUE_PROBE_SERVO_ID:-10}"
ALLOW_STATE_CHANGE="${AGENTIC_ARM_TORQUE_PROBE_ALLOW_STATE_CHANGE:-0}"
STOP_APP_NODE="${AGENTIC_TORQUE_PROBE_STOP_APP:-1}"
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

stop_app_service_if_needed() {
  if systemctl is-active --quiet start_app_node.service; then
    if [[ "$STOP_APP_NODE" != "1" ]]; then
      write_report "START_APP_NODE_ACTIVE" "start_app_node.service is active; refusing torque probe"
      return 1
    fi
    log "stopping start_app_node.service for single serial owner mode"
    sudo systemctl stop start_app_node.service
  fi
}

start_controller_owner() {
  source_ros
  mkdir -p "$LOG_DIR/raw"
  if service_active "/ros_robot_controller/bus_servo/get_state"; then
    return 0
  fi
  log "starting ros_robot_controller for torque semantics probe"
  ros2 run ros_robot_controller ros_robot_controller > "$LOG_DIR/ros_robot_controller.log" 2>&1 &
  RRC_PID="$!"
  STARTED_RRC=1
  wait_for_service "/ros_robot_controller/bus_servo/get_state"
}

read_state() {
  local label="$1"
  source_ros
  timeout 12 ros2 service call /ros_robot_controller/bus_servo/get_state \
    ros_robot_controller_msgs/srv/GetBusServoState \
    "{cmd: [{id: $SERVO_ID, get_id: 1, get_position: 1, get_voltage: 1, get_temperature: 1, get_torque_state: 1}]}" \
    > "$LOG_DIR/raw/${label}.txt" 2>&1 || true
}

set_torque_state() {
  local label="$1"
  local value="$2"
  source_ros
  timeout 8 ros2 topic pub --once /ros_robot_controller/bus_servo/set_state \
    ros_robot_controller_msgs/msg/SetBusServoState \
    "{state: [{present_id: [1, $SERVO_ID], enable_torque: [1, $value]}]}" \
    > "$LOG_DIR/raw/set_${label}.txt" 2>&1 || true
  sleep 0.3
}

torque_state_from_raw() {
  local label="$1"
  python3 - "$LOG_DIR/raw/${label}.txt" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
match = re.search(r"enable_torque=\[([^\]]*)\]", text)
if not match:
    raise SystemExit(0)
body = match.group(1).strip()
if not body:
    raise SystemExit(0)
print(body.split(",")[0].strip())
PY
}

write_report() {
  local forced_error="${1:-}"
  local forced_reason="${2:-}"
  python3 - "$LOG_DIR" "$REPORT_PATH" "$SERVO_ID" "$ALLOW_STATE_CHANGE" "$forced_error" "$forced_reason" <<'PY'
import json
import re
import sys
from pathlib import Path

log_dir = Path(sys.argv[1])
report_path = Path(sys.argv[2])
servo_id = int(sys.argv[3])
allow_state_change = sys.argv[4] == "1"
forced_error = sys.argv[5]
forced_reason = sys.argv[6]


def parse_values(text: str, field: str):
    match = re.search(rf"{field}=\[([^\]]*)\]", text)
    if not match:
        return None
    body = match.group(1).strip()
    if not body:
        return []
    out = []
    for part in body.split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return out


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
if allow_state_change:
    states["after_enable_1"] = parse_state("after_enable_1")
    states["after_enable_0"] = parse_state("after_enable_0")
    states["restored"] = parse_state("restored")

error_codes = []
reason = ""
if forced_error:
    error_codes.append(forced_error)
    reason = forced_reason
elif not allow_state_change:
    error_codes.append("TORQUE_SEMANTICS_PROBE_READ_ONLY")
    reason = "probe did not change torque state; set AGENTIC_ARM_TORQUE_PROBE_ALLOW_STATE_CHANGE=1 to test semantics"
else:
    observed = {
        "enable_1": states.get("after_enable_1", {}).get("torque_state"),
        "enable_0": states.get("after_enable_0", {}).get("torque_state"),
        "restored": states.get("restored", {}).get("torque_state"),
    }
    if observed["enable_1"] == [1] and observed["enable_0"] == [0]:
        reason = "torque_state follows enable_torque command value; physical load semantics still require operator confirmation"
    elif observed["enable_1"] == [0] and observed["enable_0"] == [1]:
        reason = "torque_state appears inverted relative to enable_torque command value; physical load semantics still require operator confirmation"
    else:
        error_codes.append("TORQUE_SEMANTICS_INCONCLUSIVE")
        reason = f"unexpected torque readback sequence: {observed}"

report = {
    "schema_version": "1.0",
    "success": not error_codes,
    "mode": "state_change_probe" if allow_state_change else "read_only",
    "servo_id": servo_id,
    "error_codes": error_codes,
    "reason": reason,
    "states": states,
    "safety_note": "This probe never sends servo positions. State-change mode only toggles bus servo torque enable for the selected servo.",
    "next_step": (
        "If physical load semantics are confirmed, set AGENTIC_ARM_TORQUE_STATE_VERIFIED=1 and AGENTIC_ARM_EXPECTED_TORQUE_STATE to the verified readable state."
    ),
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
  log "AgenticOS torque semantics probe"
  log "log_dir=$LOG_DIR"
  mkdir -p "$LOG_DIR/raw"
  stop_app_service_if_needed
  start_controller_owner
  read_state "before"
  if [[ "$ALLOW_STATE_CHANGE" == "1" ]]; then
    set_torque_state "enable_1" 1
    read_state "after_enable_1"
    set_torque_state "enable_0" 0
    read_state "after_enable_0"
    before_state="$(torque_state_from_raw before || true)"
    enable_1_state="$(torque_state_from_raw after_enable_1 || true)"
    enable_0_state="$(torque_state_from_raw after_enable_0 || true)"
    restore_command=""
    if [[ -n "$before_state" ]] && [[ "$before_state" == "$enable_1_state" ]]; then
      restore_command="1"
    elif [[ -n "$before_state" ]] && [[ "$before_state" == "$enable_0_state" ]]; then
      restore_command="0"
    fi
    if [[ -n "$restore_command" ]]; then
      set_torque_state "restore_${restore_command}" "$restore_command"
    else
      printf 'could not infer torque restore command from before=%s enable1=%s enable0=%s\n' \
        "$before_state" "$enable_1_state" "$enable_0_state" > "$LOG_DIR/raw/restore_inference_failed.txt"
    fi
    read_state "restored"
  fi
  write_report
}

main "$@"
