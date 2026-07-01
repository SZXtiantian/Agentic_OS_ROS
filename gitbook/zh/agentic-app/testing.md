# 测试 Agent App

推荐覆盖：

- manifest 字段
- 禁止 ROS2 调用
- 权限不足失败
- bridge 缺失失败
- SDK 调用顺序
- 结构化错误返回

## 命令

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/my_agent/tests
```

## 边界测试

测试应确保应用源码不包含：

- `rclpy`
- `/cmd_vel`
- `NavigateToPose`
- `MoveGroup`
- `ros2`

没有真实 bridge 时，机器人路径应返回 `ROS_BRIDGE_UNAVAILABLE` 或相关结构化错误。
