#!/usr/bin/env bash
set -euo pipefail

ROBOT_ID="${ROBOT_ID:-real_robot}"
NAV2_ACTION_NAME="${NAV2_ACTION_NAME:-/navigate_to_pose}"
PLACES_FILE="${PLACES_FILE:-/opt/agentic/etc/places.yaml}"
SAFETY_FILE="${SAFETY_FILE:-/opt/agentic/etc/safety.yaml}"
BRIDGE_PROFILE_FILE="${BRIDGE_PROFILE_FILE:-/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml}"

set +u
source /opt/ros/humble/setup.bash
if [ -f /home/ubuntu/ros2_ws/install/setup.bash ]; then
  source /home/ubuntu/ros2_ws/install/setup.bash
fi
source /home/ubuntu/agentic_ws/install/ros2_bridge/setup.bash
set -u

exec ros2 launch agentic_capability_bridge robot_test.launch.py \
  robot_id:="$ROBOT_ID" \
  nav2_action_name:="$NAV2_ACTION_NAME" \
  places_file:="$PLACES_FILE" \
  safety_file:="$SAFETY_FILE" \
  bridge_profile_file:="$BRIDGE_PROFILE_FILE"
