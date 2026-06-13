# ROS2 Bridge Integration

ROS2 remains installed at `/opt/ros/humble`.

Agentic ROS2 bridge packages live in `/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_*` and are the only Agentic layer allowed to import `rclpy`.

Runtime bridge modes:

- `mock`: default in `/opt/agentic/etc/agentic.yaml`; uses in-process mock bridge client for deterministic app tests.
- `cli`: non-`rclpy` runtime-to-bridge transport; Runtime shells out to `ros2 service call` and `ros2 action send_goal` against Agentic-owned bridge interfaces.

Use `agentic-run ... --real` with `ros_bridge_mode: cli` to exercise the ROS2 bridge path while keeping `agentic_runtime`, SDK, and Agent Apps free of `rclpy`.

`/home/ubuntu/ros2_ws/src` is reserved for robot ROS2 application packages such as calibration, drivers, navigation, perception, launch files, and robot-specific nodes. It should not contain Agentic source packages.

Build the bridge packages:

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/agentic_ws
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
```

Runtime source is in `/home/ubuntu/agentic_ws/src/agentic_runtime_src`.
Runtime install output is in `/opt/agentic`.
