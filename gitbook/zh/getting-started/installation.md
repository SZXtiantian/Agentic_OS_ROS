# 安装

Agentic OS 安装在 ROS2 旁边，而不是安装进 ROS2。推荐布局：

```text
/opt/ros/humble
/opt/agentic
/home/ubuntu/agentic_ws
/home/ubuntu/ros2_ws
```

## Runtime 开发安装

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
```

## ROS2 Bridge 构建

ROS2 bridge 是 AgenticOS-owned HAL/adapter，只允许放在 `agentic_ws/ros2_bridge_src`。

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/agentic_ws
colcon --log-base log/ros2_bridge build \
  --base-paths ros2_bridge_src \
  --build-base build/ros2_bridge \
  --install-base install/ros2_bridge
```

## 验证

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/check_agentic_app_boundaries.py agentic_apps

cd agentic_runtime_src
PYTHONPATH=. pytest -q
```

没有真实 ROS2 bridge 时，机器人能力应该返回结构化错误，而不是伪造成功。
