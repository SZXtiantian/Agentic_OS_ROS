#!/usr/bin/env bash
set -euo pipefail

ROBOT_ID="${ROBOT_ID:-real_robot}"
NAV2_ACTION_NAME="${NAV2_ACTION_NAME:-/navigate_to_pose}"
PLACES_FILE="${PLACES_FILE:-/opt/agentic/etc/places.yaml}"
SAFETY_FILE="${SAFETY_FILE:-/opt/agentic/etc/safety.yaml}"
ROBOT_PROFILE_FILE="${ROBOT_PROFILE_FILE:-/opt/agentic/etc/robot_profiles/rosorin_arm_camera.yaml}"

set +u
source /opt/ros/humble/setup.bash
if [ -f /home/ubuntu/ros2_ws/install/setup.bash ]; then
  source /home/ubuntu/ros2_ws/install/setup.bash
fi
source /home/ubuntu/agentic_ws/install/system_skill_nodes/setup.bash
set -u

exec ros2 launch agentic_capability_bridge robot_test.launch.py \
  robot_id:="$ROBOT_ID" \
  nav2_action_name:="$NAV2_ACTION_NAME" \
  places_file:="$PLACES_FILE" \
  safety_file:="$SAFETY_FILE" \
  bridge_profile_file:="$ROBOT_PROFILE_FILE"
