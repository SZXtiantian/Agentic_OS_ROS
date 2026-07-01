# Architecture Boundaries

Agentic OS is not a ROS2 fork and does not place business nodes inside ROS2.

## Forbidden

- Do not modify `/opt/ros/*`, ROS2 upstream, Nav2 upstream, MoveIt upstream, or robot vendor driver source.
- Agentic Runtime must not import `rclpy`.
- Agent Apps must not import `rclpy`.
- Agent Apps must not publish `/cmd_vel`.
- Agent Apps must not subscribe to `/scan`, `/odom`, or `/tf` directly.
- Agent Apps must not call Nav2 or MoveIt actions directly.

## Allowed location

Only ROS2 bridge packages may import `rclpy`, and they must live under:

```text
/home/ubuntu/agentic_ws/ros2_bridge_src/*
```

These bridges are Agentic OS-owned HAL/adapters, not Agent App workspaces.
