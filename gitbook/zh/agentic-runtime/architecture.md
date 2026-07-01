# 架构边界

Agentic OS 不是 ROS2 fork，也不是把业务节点塞进 ROS2。

## 禁止事项

- 不修改 `/opt/ros/*`、ROS2 upstream、Nav2 upstream、MoveIt upstream 或机器人厂商驱动源码。
- Agentic Runtime 不导入 `rclpy`。
- Agent App 不导入 `rclpy`。
- Agent App 不发布 `/cmd_vel`。
- Agent App 不直接订阅 `/scan`、`/odom`、`/tf`。
- Agent App 不直接调用 Nav2 或 MoveIt action。

## 允许的位置

只有 ROS2 bridge packages 可以导入 `rclpy`，并且必须位于：

```text
/home/ubuntu/agentic_ws/ros2_bridge_src/*
```

这些 bridge 是 Agentic OS-owned HAL/adapter，不是 Agent App workspace。
