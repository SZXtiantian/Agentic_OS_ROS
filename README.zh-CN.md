<h1 align="center">Agentic OS ROS</h1>

<p align="center">
  <a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="agentic_runtime_src/"><img src="https://img.shields.io/badge/runtime-real--only-2f6f5e" alt="Runtime real-only"></a>
  <a href="ros2_bridge_src/"><img src="https://img.shields.io/badge/ROS2-Humble-3b6ea8" alt="ROS2 Humble"></a>
  <a href="agentic_apps/"><img src="https://img.shields.io/badge/Agent%20Apps-no%20rclpy-bc5b45" alt="Agent Apps do not import rclpy"></a>
  <a href="agentic_runtime_src/docs/access_audit.md"><img src="https://img.shields.io/badge/safety-audit%20logged-7c5c9e" alt="Safety and audit"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-4f6f9f" alt="Apache 2.0 license"></a>
</p>

<p align="center">
  <img src="assets/agentic-os-ros-concept.png" alt="Agentic OS ROS concept image" width="880">
</p>

**Agentic OS ROS** 是运行在 ROS2 之上的 Agentic Runtime / Agentic OS 项目。它为 Agent App 提供一个高层机器人能力入口，同时由 Agentic Runtime 负责安全、权限、生命周期控制和审计。

---

## 项目提供什么

- **Agentic Runtime / Kernel**：权限、调度、内存、上下文、存储、技能和审计等 Runtime 服务。
- **Agentic SDK**：面向 Agent App 的高层 API。
- **Robot Capability Layer**：带策略约束的机器人任务能力分发。
- **ROS2 Bridge Packages**：AgenticOS 拥有的 Runtime 与 ROS2 适配层。
- **Agent App 模板和示例**：用于开发原生 Agent App 的起点。

---

## 架构边界

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Robot Capability Layer
  -> AgenticOS ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

核心边界很简单：Agent App 和 Runtime 位于 ROS2 之上；ROS2 相关代码只放在 AgenticOS 拥有的 bridge package 中。

---

## 目录结构

| 路径 | 职责 |
| --- | --- |
| `agentic_runtime_src/` | Runtime、Kernel、SDK、配置、脚本、测试和文档 |
| `agentic_apps/` | Agent App 模板和示例 |
| `ros2_bridge_src/` | AgenticOS 拥有的 ROS2 bridge package |
| `robot_descriptions/` | 机器人描述和可视化资源 |
| `scripts/` | 工作区级检查和测试入口 |
| `assets/` | README 和文档图片 |

---

## 快速开始

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
scripts/run_tests.sh
scripts/verify_agentic_app_tutorials.sh
```

Runtime 开发：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
PYTHONPATH=. pytest -q
```

---

## 安全原则

- Agentic Runtime 与 ROS2 应用包保持分离。
- ROS2 相关 import 只放在 bridge package 中。
- 实时控制仍由 ROS2 controller、Nav2、MoveIt 或厂商驱动负责。
- 机器人动作通过 Runtime 权限、资源归属、安全检查和审计。
- 不提交密钥、运行时状态、审计日志、真实采集数据或生成的运行输出。

---

## 开源协议

本项目使用 Apache License, Version 2.0 开源。详见 [LICENSE](LICENSE)。
