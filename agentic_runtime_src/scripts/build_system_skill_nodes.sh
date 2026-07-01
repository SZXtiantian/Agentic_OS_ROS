#!/usr/bin/env bash
set -euo pipefail

set +u
source /opt/ros/humble/setup.bash
if [ -f /home/ubuntu/ros2_ws/install/setup.bash ]; then
  source /home/ubuntu/ros2_ws/install/setup.bash
fi
set -u

cd /home/ubuntu/agentic_ws
colcon --log-base log/system_skill_nodes build \
  --base-paths ros2_bridge_src \
  --build-base build/system_skill_nodes \
  --install-base install/system_skill_nodes \
  --packages-select \
  agentic_msgs \
  agentic_world_model \
  agentic_safety_guard \
  agentic_capability_bridge \
  agentic_app_runtime_bridge

echo "AgenticOS system skill nodes built."
echo "Start robot skills with:"
echo "  /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_skills.sh"
