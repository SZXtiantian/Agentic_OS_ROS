#!/usr/bin/env bash
set -euo pipefail

RUNTIME_SRC="/home/ubuntu/agentic_ws/src/agentic_runtime_src"
APP_DIR="/home/ubuntu/agentic_ws/src/robot_photographer_agent"
AGENTIC_HOME="${AGENTIC_HOME:-/opt/agentic}"
PROFILE="${ROBOT_PROFILE_FILE:-$AGENTIC_HOME/etc/robot_profiles/rosorin_arm_camera.yaml}"
ALLOW_ARM="${AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION:-0}"
STATUS=0
ARM_HEALTH_OK=0

log() {
  printf '\n[%s] %s\n' "$(date -Is)" "$*"
}

json_event() {
  local status="$1"
  local code="$2"
  local detail="$3"
  printf '{"status":"%s","code":"%s","detail":"%s"}\n' "$status" "$code" "$detail"
}

soft() {
  log "$*"
  if ! "$@"; then
    STATUS=1
    json_event "failed" "COMMAND_FAILED" "$*"
  fi
}

source_ros() {
  set +u
  source /opt/ros/humble/setup.bash
  if [[ -f /home/ubuntu/ros2_ws/install/setup.bash ]]; then
    source /home/ubuntu/ros2_ws/install/setup.bash
  fi
  if [[ -f /home/ubuntu/agentic_ws/install/system_skill_nodes/setup.bash ]]; then
    source /home/ubuntu/agentic_ws/install/system_skill_nodes/setup.bash
  fi
  set -u
}

check_action_groups() {
  log "camera pose backend availability"
  python - "$PROFILE" <<'PY'
import json
import sys
from pathlib import Path

import yaml

profile = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8")) or {}
arm = profile.get("arm") or {}
root = Path(arm.get("action_group_path") or "/home/ubuntu/software/arm_pc/ActionGroups")
  required = [
    "camera_center",
    "camera_yaw_left_15",
    "camera_yaw_right_15",
    "camera_pitch_up_15",
    "arm_home",
]
actions = arm.get("allowed_named_actions") or {}
missing = []
availability = {}
for name in required:
    spec = actions.get(name) or {}
    backend_action = spec.get("backend_action", name)
    path = root / f"{backend_action}.d6a"
    exists = path.exists()
    availability[name] = {
        "backend_action": backend_action,
        "path": str(path),
        "exists": exists,
    }
    if not exists:
        missing.append(name)
print(json.dumps({"availability": availability, "missing": missing}, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(1 if missing else 0)
PY
}

ros_graph_checks() {
  source_ros
  log "ROS graph checks"
  timeout 8 ros2 node list 2>&1 | grep -E '/manipulation_bridge_node|/servo_manager|/controller_manager|/aurora|/ros_robot_controller' || true
  timeout 8 ros2 topic list -t 2>&1 | grep -E '/servo_controller|/depth_cam/rgb0/image_raw|/camera/color/image_raw' || true
  timeout 8 ros2 service list -t 2>&1 | grep -E '/agentic/arm/get_state|/agentic/robot/stop|/agentic/perception/capture_photo|/agentic/safety/check' || true
}

arm_health_gate() {
  log "read-only arm hardware health gate"
  if "$RUNTIME_SRC/scripts/real_robot_arm_health_gate.sh"; then
    ARM_HEALTH_OK=1
    json_event "ok" "ARM_HEALTH_GATE_PASSED" "real robot arm health gate passed"
  else
    ARM_HEALTH_OK=0
    STATUS=1
    json_event "failed" "ARM_HEALTH_GATE_FAILED" "health gate failed; real arm motion will not be attempted"
  fi
}

restart_agentic_bridge() {
  source_ros
  log "restarting AgenticOS bridge processes"
  python - <<'PY'
import os
import signal
import subprocess
import time

patterns = (
    "ros2 launch agentic_capability_bridge robot_test.launch.py",
    "/home/ubuntu/agentic_ws/install/system_skill_nodes/agentic_",
)
current = os.getpid()
pids = []
for line in subprocess.check_output(["ps", "-eo", "pid=,cmd="], text=True).splitlines():
    line = line.strip()
    if not line:
        continue
    pid_text, _, cmd = line.partition(" ")
    try:
        pid = int(pid_text)
    except ValueError:
        continue
    if pid == current:
        continue
    if any(pattern in cmd for pattern in patterns):
        pids.append(pid)
for pid in pids:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
if pids:
    time.sleep(2.0)
for pid in pids:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        continue
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
print({"terminated_agentic_bridge_pids": pids})
PY
}

ensure_bridge() {
  source_ros
  if timeout 8 ros2 service list -t 2>/dev/null | grep -q '^/agentic/perception/capture_photo '; then
    json_event "ok" "BRIDGE_ALREADY_RUNNING" "/agentic/perception/capture_photo"
    return
  fi
  log "starting AgenticOS bridge"
  /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_skills.sh >/tmp/agentic_multi_angle_bridge.log 2>&1 &
  for _ in {1..80}; do
    if timeout 5 ros2 service list -t 2>/dev/null | grep -q '^/agentic/perception/capture_photo '; then
      json_event "ok" "BRIDGE_STARTED" "$!"
      return
    fi
    sleep 0.5
  done
  STATUS=1
  json_event "failed" "BRIDGE_UNAVAILABLE" "see /tmp/agentic_multi_angle_bridge.log"
}

main() {
  test -f "$RUNTIME_SRC/AGENTS.md"
  test -f "$APP_DIR/app.yaml"
  test -f "$PROFILE"

  soft "$AGENTIC_HOME/bin/agenticctl" status --real
  soft "$RUNTIME_SRC/scripts/build_system_skill_nodes.sh"
  restart_agentic_bridge
  soft python "$RUNTIME_SRC/scripts/check_forbidden_imports.py"
  soft python "$RUNTIME_SRC/scripts/check_camera_pose_action_groups.py" "$PROFILE"
  soft env AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=0 "$RUNTIME_SRC/scripts/run_tests.sh"
  soft env AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=0 pytest -q "$APP_DIR/tests"
  soft check_action_groups
  arm_health_gate
  ros_graph_checks
  ensure_bridge

  soft "$AGENTIC_HOME/bin/agentic" photo --real --json "拍一张照片"

  if [[ "$ALLOW_ARM" == "1" ]]; then
    if [[ "$ARM_HEALTH_OK" == "1" ]]; then
      soft "$AGENTIC_HOME/bin/agentic" photo --real --allow-arm-motion --yes --json "拍一组多角度照片并验证差异"
    else
      STATUS=1
      json_event "failed" "ARM_HEALTH_GATE_FAILED" "AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 was set, but health gate failed; refusing real multi-angle arm motion"
    fi
  else
    json_event "skipped" "ARM_MOTION_DISABLED" "set AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 for real multi-angle capture"
  fi

  soft "$AGENTIC_HOME/bin/agentic" photo --real --json "停止"
  log "latest sessions"
  "$AGENTIC_HOME/bin/agenticctl" sessions --limit 8 || true
  log "latest audit"
  "$AGENTIC_HOME/bin/agenticctl" audit --limit 20 || true
  log "latest verification files"
  find "$APP_DIR/storage/runs" -maxdepth 2 -name 'verification.json' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 5 || true
  exit "$STATUS"
}

main "$@"
