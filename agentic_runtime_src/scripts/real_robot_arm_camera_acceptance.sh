#!/usr/bin/env bash
set -euo pipefail

RUNTIME_SRC="/home/ubuntu/agentic_ws/src/agentic_runtime_src"
AGENTIC_HOME="${AGENTIC_HOME:-/opt/agentic}"
PROFILE="${BRIDGE_PROFILE_FILE:-$AGENTIC_HOME/etc/bridge_profiles/rosorin_arm_camera.yaml}"
TARGET="${AGENTIC_ACCEPTANCE_TARGET:-workspace}"
ALLOW_ARM="${AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION:-0}"
BRIDGE_PID=""
ACCEPTANCE_STATUS=0

log() {
  printf '\n[%s] %s\n' "$(date -Is)" "$*"
}

json_event() {
  local status="$1"
  local code="$2"
  local detail="$3"
  printf '{"status":"%s","code":"%s","detail":"%s"}\n' "$status" "$code" "$detail"
}

cleanup() {
  if [[ -n "$BRIDGE_PID" ]] && kill -0 "$BRIDGE_PID" >/dev/null 2>&1; then
    kill "$BRIDGE_PID" >/dev/null 2>&1 || true
    wait "$BRIDGE_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

run_required() {
  log "$*"
  "$@"
}

run_soft() {
  log "$*"
  if ! "$@"; then
    ACCEPTANCE_STATUS=1
    json_event "failed" "COMMAND_FAILED" "$*"
  fi
}

source_ros() {
  set +u
  source /opt/ros/humble/setup.bash
  if [[ -f /home/ubuntu/ros2_ws/install/setup.bash ]]; then
    source /home/ubuntu/ros2_ws/install/setup.bash
  fi
  if [[ -f /home/ubuntu/third_party/aurora_ws/install/setup.bash ]]; then
    source /home/ubuntu/third_party/aurora_ws/install/setup.bash
  fi
  if [[ -f /home/ubuntu/third_party/third_party_ws/install/setup.bash ]]; then
    source /home/ubuntu/third_party/third_party_ws/install/setup.bash
  fi
  if [[ -f /home/ubuntu/third_party/orbbec_ws/install/setup.bash ]]; then
    source /home/ubuntu/third_party/orbbec_ws/install/setup.bash
  fi
  if [[ -f /home/ubuntu/agentic_ws/install/ros2_bridge/setup.bash ]]; then
    source /home/ubuntu/agentic_ws/install/ros2_bridge/setup.bash
  fi
  set -u
}

robot_process_snapshot() {
  ps -eo pid,ppid,stat,etime,cmd \
    | grep -E 'aurora930_node|orbbec|usb_cam|servo_controller|ros_robot_controller|openclaw|kinematics|claw_arm' \
    | grep -v grep || true
}

camera_usb_snapshot() {
  echo "lsusb:"
  if command -v lsusb >/dev/null 2>&1; then
    lsusb 2>&1 || true
    echo "lsusb -t:"
    lsusb -t 2>&1 || true
  else
    echo "lsusb command not found"
  fi
  echo "usb device nodes:"
  if [[ -d /dev/bus/usb ]]; then
    find /dev/bus/usb -type c -printf '%p %m %u:%g\n' 2>&1 | sort || true
  else
    echo "/dev/bus/usb not visible"
  fi
}

active_ipv4_snapshot() {
  ip -o -4 addr show 2>/dev/null | awk '{split($4, addr, "/"); print addr[1]}' | sort -u || true
}

dds_socket_snapshot() {
  ss -H -ulpn 2>/dev/null \
    | grep -E 'aurora930_node|servo_controlle|ros_robot_contr|static_transfor|robot_state_pub|joint_state_pub|apply_calib|imu_filter|web_video_serve|scan_to_scan|agentic_' \
    || true
}

stale_dds_locators() {
  local active_ips
  active_ips="$(active_ipv4_snapshot)"
  dds_socket_snapshot | while read -r line; do
    local local_addr
    local_addr="$(printf '%s\n' "$line" | awk '{print $4}' | sed -E 's/:([0-9]+)$//')"
    case "$local_addr" in
      ""|"0.0.0.0"|"127."*) continue ;;
    esac
    if ! printf '%s\n' "$active_ips" | grep -Fxq "$local_addr"; then
      printf '%s\n' "$line"
    fi
  done
}

ros_graph_snapshot() {
  source_ros
  {
    echo "nodes:"
    timeout 8 ros2 node list --no-daemon 2>&1 || true
    echo "topics:"
    timeout 8 ros2 topic list -t --no-daemon 2>&1 || true
    echo "services:"
    timeout 8 ros2 service list -t --no-daemon 2>&1 || true
    echo "node_info:/aurora"
    timeout 8 ros2 node info /aurora --no-daemon 2>&1 || true
    echo "node_info:/init_pose"
    timeout 8 ros2 node info /init_pose --no-daemon 2>&1 || true
    echo "node_info:/servo_manager"
    timeout 8 ros2 node info /servo_manager --no-daemon 2>&1 || true
  }
}

local_ros_discovery_smoke() {
  source_ros
  local log="/tmp/agentic_local_ros_discovery_smoke.log"
  local pid=""
  log "local ROS graph discovery smoke test"
  ros2 run demo_nodes_py talker > "$log" 2>&1 &
  pid="$!"
  sleep 3
  if timeout 8 ros2 topic list -t --no-daemon 2>/dev/null | grep -q '^/chatter '; then
    json_event "ok" "ROS_GRAPH_LOCAL_DISCOVERY_OK" "fresh local /chatter publisher is discoverable"
  else
    ACCEPTANCE_STATUS=1
    json_event "failed" "ROS_GRAPH_LOCAL_DISCOVERY_FAILED" "fresh local /chatter publisher was not discoverable; see $log"
  fi
  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" >/dev/null 2>&1 || true
}

ensure_bridge() {
  source_ros
  if ros2 service list --no-daemon 2>/dev/null | grep -q '^/agentic/perception/observe$'; then
    json_event "ok" "BRIDGE_ALREADY_RUNNING" "/agentic/perception/observe"
    return
  fi
  log "starting AgenticOS bridge nodes"
  ros2 launch agentic_capability_bridge robot_test.launch.py \
    robot_id:=rosorin_real_robot \
    places_file:="$AGENTIC_HOME/etc/places.yaml" \
    safety_file:="$AGENTIC_HOME/etc/safety.yaml" \
    bridge_profile_file:="$PROFILE" > /tmp/agentic_arm_camera_bridge.log 2>&1 &
  BRIDGE_PID="$!"
  for _ in {1..40}; do
    if ros2 service list --no-daemon 2>/dev/null | grep -q '^/agentic/perception/observe$'; then
      json_event "ok" "BRIDGE_STARTED" "$BRIDGE_PID"
      return
    fi
    sleep 0.25
  done
  ACCEPTANCE_STATUS=1
  json_event "failed" "BRIDGE_UNAVAILABLE" "AgenticOS bridge services did not appear; see /tmp/agentic_arm_camera_bridge.log"
}

probe_ros_graph() {
  source_ros
  local graph
  local processes
  processes="$(robot_process_snapshot)"
  graph="$(ros_graph_snapshot)"
  log "robot process snapshot"
  printf '%s\n' "$processes"
  if [[ -z "$processes" ]]; then
    ACCEPTANCE_STATUS=1
    json_event "failed" "ROBOT_BRINGUP_NOT_RUNNING" "no camera/arm vendor bringup processes matched expected real-robot candidates"
  fi
  if [[ -n "$processes" ]] && ! printf '%s\n' "$graph" | grep -Eq '/depth_cam/rgb0/image_raw|/camera/color/image_raw|/servo_controller|/ros_robot_controller/bus_servo/set_position|/init_pose|/servo_manager|/claw_arm_group_control|/kinematics'; then
    ACCEPTANCE_STATUS=1
    json_event "failed" "ROS_GRAPH_DISCOVERY_INCOMPLETE" "robot processes are running, but ROS CLI graph discovery sees no configured camera/arm interfaces"
  fi
  log "DDS locator snapshot"
  local active_ips
  active_ips="$(active_ipv4_snapshot)"
  printf 'active_ipv4:\n%s\n' "$active_ips"
  local dds_sockets
  dds_sockets="$(dds_socket_snapshot)"
  printf 'dds_sockets:\n%s\n' "$dds_sockets"
  local stale_sockets
  stale_sockets="$(stale_dds_locators)"
  if [[ -n "$stale_sockets" ]]; then
    ACCEPTANCE_STATUS=1
    printf 'stale_dds_locators:\n%s\n' "$stale_sockets"
    json_event "failed" "ROS_GRAPH_DDS_LOCATOR_STALE" "vendor DDS sockets are bound to IPv4 addresses that are no longer active; restart robot bringup after network settles"
  fi
  log "camera USB snapshot"
  local usb_snapshot
  usb_snapshot="$(camera_usb_snapshot)"
  printf '%s\n' "$usb_snapshot"
  if ! printf '%s\n' "$usb_snapshot" | grep -q '3251:1930'; then
    ACCEPTANCE_STATUS=1
    json_event "failed" "CAMERA_USB_DEVICE_MISSING" "Aurora 930 USB id 3251:1930 not visible"
  fi
  log "ROS graph camera topics"
  if ! printf '%s\n' "$graph" | grep -E 'image_raw|camera_info|points|depth|camera|rgb'; then
    ACCEPTANCE_STATUS=1
    json_event "failed" "CAMERA_TOPICS_MISSING" "no configured camera topics visible"
  fi
  log "ROS graph arm topics/services"
  if ! printf '%s\n' "$graph" | grep -E 'servo|joint|controller|claw|arm'; then
    json_event "warn" "ARM_TOPICS_MISSING" "arm topics not visible before bringup"
  fi
  if ! printf '%s\n' "$graph" | grep -E 'kinematics|pose|joint|claw|servo|arm'; then
    json_event "warn" "ARM_SERVICES_MISSING" "arm services not visible before bringup"
  fi
}

observe_camera() {
  source_ros
  log "camera observation service"
  local output
  if ! output="$(ros2 service call /agentic/perception/observe agentic_msgs/srv/Observe "{target: '$TARGET', request_id: 'acceptance_observe', timeout_s: 5}" 2>&1)"; then
    ACCEPTANCE_STATUS=1
    printf '%s\n' "$output"
    json_event "failed" "OBSERVE_SERVICE_FAILED" "/agentic/perception/observe call failed"
    return
  fi
  printf '%s\n' "$output"
  if printf '%s\n' "$output" | grep -q "CAMERA_UNAVAILABLE"; then
    ACCEPTANCE_STATUS=1
    json_event "failed" "CAMERA_UNAVAILABLE" "bridge returned truthful camera unavailable"
  fi
}

run_agent() {
  log "camera_arm_inspection_agent read-only run"
  set +e
  "$AGENTIC_HOME/bin/agentic-run" camera_arm_inspection_agent --real --place "$TARGET" --json
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    ACCEPTANCE_STATUS=1
    json_event "failed" "AGENT_RUN_FAILED" "camera_arm_inspection_agent returned non-zero"
  fi
}

maybe_move_arm() {
  source_ros
  if [[ "$ALLOW_ARM" != "1" ]]; then
    json_event "skipped" "ARM_MOTION_DISABLED" "set AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 to run camera_up"
    return
  fi
  log "optional safe named arm action"
  local output
  if ! output="$(ros2 action send_goal /agentic/arm/move_named agentic_msgs/action/MoveArmNamed "{name: 'camera_up', request_id: 'acceptance_arm', timeout_s: 8}" --feedback 2>&1)"; then
    ACCEPTANCE_STATUS=1
    printf '%s\n' "$output"
    json_event "failed" "ARM_ACTION_FAILED" "camera_up action failed"
    return
  fi
  printf '%s\n' "$output"
}

stop_evidence() {
  source_ros
  log "stop/cancel evidence"
  local output
  if ! output="$(ros2 service call /agentic/robot/stop agentic_msgs/srv/StopRobot "{reason: 'acceptance_stop_probe', request_id: 'acceptance_stop'}" 2>&1)"; then
    ACCEPTANCE_STATUS=1
    printf '%s\n' "$output"
    json_event "failed" "STOP_SERVICE_FAILED" "/agentic/robot/stop call failed"
    return
  fi
  printf '%s\n' "$output"
}

latest_evidence() {
  log "latest sessions"
  "$AGENTIC_HOME/bin/agenticctl" sessions --limit 5 || true
  log "latest audit"
  "$AGENTIC_HOME/bin/agenticctl" audit --limit 20 || true
}

main() {
  test -f "$RUNTIME_SRC/AGENTS.md"
  test -f "$PROFILE" || {
    ACCEPTANCE_STATUS=1
    json_event "failed" "PROFILE_MISSING" "$PROFILE"
  }
  run_soft "$AGENTIC_HOME/bin/agenticctl" status --real
  run_required "$RUNTIME_SRC/scripts/build_robot_bridge.sh"
  probe_ros_graph
  run_soft python "$RUNTIME_SRC/scripts/check_forbidden_imports.py"
  run_soft python "$RUNTIME_SRC/scripts/check_filesystem_layout.py"
  run_soft "$RUNTIME_SRC/scripts/run_tests.sh"
  local_ros_discovery_smoke
  ensure_bridge
  observe_camera
  run_agent
  maybe_move_arm
  stop_evidence
  latest_evidence
  exit "$ACCEPTANCE_STATUS"
}

main "$@"
