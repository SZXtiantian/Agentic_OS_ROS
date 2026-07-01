# Installation

Agentic OS is installed beside ROS2, not inside ROS2. Recommended layout:

```text
/opt/ros/humble
/opt/agentic
/home/ubuntu/agentic_ws
/home/ubuntu/ros2_ws
```

## Runtime Development Install

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
```

## Build ROS2 Bridges

ROS2 bridges are AgenticOS-owned HAL/adapters and must live under `agentic_ws/ros2_bridge_src`.

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/agentic_ws
colcon --log-base log/ros2_bridge build \
  --base-paths ros2_bridge_src \
  --build-base build/ros2_bridge \
  --install-base install/ros2_bridge
```

## Verify

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/check_agentic_app_boundaries.py agentic_apps

cd agentic_runtime_src
PYTHONPATH=. pytest -q
```

Without a real ROS2 bridge, robot capabilities should return structured errors rather than fabricated success.
