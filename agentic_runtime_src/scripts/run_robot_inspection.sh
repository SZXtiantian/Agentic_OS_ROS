#!/usr/bin/env bash
set -euo pipefail

PLACE="${1:-厨房}"

set +u
source /opt/ros/humble/setup.bash
source /home/ubuntu/agentic_ws/install/ros2_bridge/setup.bash
source /opt/agentic/setup.bash >/dev/null
set -u

export AGENTIC_RUNTIME_CONFIG=/opt/agentic/etc/agentic_robot.yaml

/opt/agentic/bin/agentic-run inspection_agent --place "$PLACE" --real
