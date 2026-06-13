#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/agentic_ws
set +u
source /opt/ros/humble/setup.bash
set -u
colcon --log-base log/ros2_bridge build \
  --base-paths ros2_bridge_src \
  --build-base build/ros2_bridge \
  --install-base install/ros2_bridge \
  --packages-select \
  agentic_msgs \
  agentic_world_model \
  agentic_safety_guard \
  agentic_capability_bridge \
  agentic_app_runtime_bridge

echo "ROS2 bridge packages built. Start nodes with:"
echo "source /home/ubuntu/agentic_ws/install/ros2_bridge/setup.bash"
echo "ros2 launch agentic_capability_bridge robot_test.launch.py"
