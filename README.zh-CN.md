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
- **环境感知 DAG Scheduler**：显式 kernel policy
  `env_aware_priority_dag`，用于全局 TaskGraph 调度、事实复用、资源租约、
  生命周期联动、审计和 debug export。
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
scripts/verify_foundation.sh
scripts/verify_capability_truth.sh
scripts/verify_no_fake_mock.sh
```

Runtime 开发：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
PYTHONPATH=. pytest -q
```

环境感知调度器文档见
[`agentic_runtime_src/docs/scheduler_environment_aware_dag.md`](agentic_runtime_src/docs/scheduler_environment_aware_dag.md)。
真实 scheduler LLM 和 capability 验证脚本需要显式开启；在真实 provider、
bridge 和 capability backend 尚未配置时，会返回
`UNVERIFIED_REAL_DEPENDENCY`。如果 scheduler capability bridge 缺失，会以
稳定的 `ROS_SERVICE_UNAVAILABLE` 或 `ROS_ACTION_UNAVAILABLE` 报告；capability
验证脚本会在 `NEXT_ACTION` 中给出所需接口、可见 ROS graph 数量和查询命令，
例如 `required=/agentic/robot/get_state`、`visible_services=0` 和
`command=ros2 service list`，并提示
`start_command=ros2 run agentic_capability_bridge state_bridge_node`。对这个只读
state service，它还会报告 bridge 可执行文件探测结果，例如
`bridge_executable=agentic_capability_bridge/state_bridge_node:available`
和 `executable_command=ros2 pkg executables agentic_capability_bridge`。默认情况下
验证脚本不会启动 ROS 节点；设置 `AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE=1`
时，才会在本次检查期间临时启动真实只读 `state_bridge_node`。backend unavailable
结果还会包含精简的 `ros_graph=` 证据，显示 live node/topic/service/action 数量以及
已配置 camera/arm/gripper topic 的可见性，并从所选 robot profile 输出
`profile_dependencies=`，展示候选 camera launch 文件、arm topics/services 和
action-group 文件存在比例，包括 `camera_backend=`、`arm_backend=`、
`gripper_backend=`、`camera_launch_files_present=` 和 `next_backend_steps=`
动作标签；`backend_step_hints=` 会把这些标签映射成非自动执行的 operator
指引，例如使用只读 state-bridge opt-in、启动 profile 中的 camera launch，或执行
需要人工确认的真实 arm/servo 启动。验证脚本不会自动执行这些后端启动动作。ROS discovery 重试窗口由
`AGENTIC_VERIFY_ROS_DISCOVERY_ATTEMPTS` 和
`AGENTIC_VERIFY_ROS_DISCOVERY_RETRY_DELAY_S` 控制。当前通用水杯
检测、抓取、持有验证和递送 backend 仍是真实 capability 缺口；在这些真实 bridge/HAL
路径存在前，scheduler 水杯复用必须保持 unavailable。

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
