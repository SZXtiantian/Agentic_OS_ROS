#!/usr/bin/env bash

export AGENTIC_WS=/home/ubuntu/agentic_ws
export AGENTIC_RUNTIME_SRC=$AGENTIC_WS/src/agentic_runtime_src
export AGENTIC_ROS2_BRIDGE_SRC=$AGENTIC_WS/ros2_bridge_src
export PYTHONPATH=$AGENTIC_RUNTIME_SRC:$PYTHONPATH
export AGENTIC_APP_ROOT=$AGENTIC_WS/src

echo "Agentic workspace loaded from $AGENTIC_WS"
