<h1 align="center">Agentic OS ROS</h1>

<p align="center">
  <a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="agentic_runtime_src/"><img src="https://img.shields.io/badge/runtime-real--only-2f6f5e" alt="Runtime real-only"></a>
  <a href="ros2_bridge_src/"><img src="https://img.shields.io/badge/ROS2-Humble-3b6ea8" alt="ROS2 Humble"></a>
  <a href="agentic_apps/"><img src="https://img.shields.io/badge/Agent%20Apps-no%20rclpy-bc5b45" alt="Agent Apps do not import rclpy"></a>
  <a href="agentic_runtime_src/docs/access_audit.md"><img src="https://img.shields.io/badge/safety-audit%20logged-7c5c9e" alt="Safety and audit"></a>
</p>

<p align="center">
  <img src="assets/agentic-os-ros-concept.png" alt="Agentic OS ROS concept image" width="880">
</p>

**Agentic OS ROS** 是运行在 ROS2 之上的 Agentic Runtime / Agentic OS 源码树。它不是普通 ROS2 应用，不是 LLM 包装器，也不是 ROS2、Nav2 或 MoveIt 的 fork。它的目标是在机器人原有 ROS2 能力之上，向 Agent App 暴露高层、受权限约束、可审计、可安全停止的机器人能力。

Agent App 不直接接触 `/cmd_vel`、`/scan`、`/odom`、`/tf`、Nav2 action 或 MoveIt action。所有危险动作必须经过 Runtime 的权限检查、资源锁、安全守卫和审计日志，再由 AgenticOS 拥有的 ROS2 Bridge / HAL 适配到 ROS2。

---

## 项目提供什么

- **Agentic Runtime / Kernel**：系统调用生命周期、调度、内存、上下文、存储、工具、技能、权限和审计的核心实现。
- **Agentic SDK**：给 Agent App 使用的高层 API，例如 `ctx.robot.navigate_to(place)` 和 `ctx.memory.remember(key, value)`。
- **Robot Capability Layer**：把任务级能力映射到权限、资源、安全策略和具体 bridge 后端。
- **ROS2 Bridge Packages**：唯一允许 `rclpy` 的 AgenticOS 适配层，用于连接 ROS2 service、action、topic、Nav2、MoveIt 或厂商驱动。
- **Agent App 示例和模板**：包含 `hello_world_agent`、`color_block_grasper_agent`、`robot_photographer_agent` 等示例，以及可复制的 `app_template`。
- **Real-only 验证路径**：生产路径不伪造模拟成功；缺失真实依赖时返回稳定错误码，例如 `ROS_BRIDGE_UNAVAILABLE`、`LLM_PROVIDER_UNCONFIGURED` 或 `UNVERIFIED_REAL_DEPENDENCY`。

---

## 当前机器人能力路径

当前真实机器人操作路径是原生 `color_block_grasper_agent`。它在需要时通过 Runtime 拥有的 LLM facade 规划任务，由 Agent App 做策略校验，然后调用 Agentic Runtime 拥有的高层技能：

- `perception.center_color_block` 通过 ROS2 bridge 在抓取规划前对齐目标色块。
- `perception.detect_color_block` 记录抓取前证据和带深度信息的目标元数据。
- `manipulation.pick_color_block` 通过 bridge action 执行受保护的机械臂和夹爪动作序列。
- `perception.verify_held_color_block` 使用 ROI、尺寸、位置和深度差检查验证抓取后证据。
- `manipulation.place_color_block` 和 `manipulation.open_gripper` 完成 allowlist 约束下的放置流程。

这些能力仍然是 real-only：如果相机帧、深度数据、servo bridge subscriber、LLM 配置或操作员权限不可用，Runtime 会返回结构化错误，而不是伪造成功。

---

## 架构

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Permission Checks / Resource Locks / Safety Guards / Audit Logs
  -> Robot Capability Layer
  -> AgenticOS Hardware Adapter / ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

边界规则：

- Agent App 和 Runtime 都不能 import `rclpy`。
- Agent App 不能发布 `/cmd_vel`。
- Agent App 不能直接订阅 `/scan`、`/odom` 或 `/tf`。
- Agent App 不能直接调用 Nav2 或 MoveIt action。
- 只有 `ros2_bridge_src/*` 下的 ROS2 bridge package 可以 import `rclpy`。
- LLM / Agent 逻辑不能执行实时闭环控制。
- `/home/ubuntu/ros2_ws/src` 保留给传统机器人 ROS2 应用包。
- `/opt/agentic` 是安装后的 AgenticOS 系统根目录，保存 bridge 配置、已安装 runtime、技能、审计、日志和运行时状态。

---

## Foundation API Surface

Agent App 只能通过高层上下文 API 使用机器人和系统能力：

```python
ctx.robot.get_state()
ctx.robot.navigate_to(place)
ctx.robot.inspect_area(place)
ctx.robot.stop()
ctx.world.resolve_place(name)
ctx.memory.remember(key, value)
ctx.memory.recall(key)
ctx.human.ask(question)
ctx.report.say(message)
```

---

## 目录结构

| 路径 | 职责 |
| --- | --- |
| `agentic_runtime_src/` | Runtime、Kernel、SDK、系统调用、调度、权限、审计、LLM facade、技能 manifest、配置、脚本、测试和文档 |
| `agentic_apps/` | Agent App 示例和模板；新增 Agent App 应从 `agentic_apps/app_template` 复制开始 |
| `ros2_bridge_src/` | AgenticOS 拥有的 ROS2 bridge / HAL package；这是本仓库中唯一允许 `rclpy` 的源码区域 |
| `robot_descriptions/` | 机器人描述、URDF / xacro、mesh 和 RViz 相关资源 |
| `scripts/` | 工作区级静态检查和测试入口 |
| `assets/` | README 和文档使用的图片资源 |

---

## 快速开始

安装 Runtime 开发依赖并运行单元测试：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
PYTHONPATH=. pytest -q
```

运行工作区静态检查和基础测试：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
scripts/run_tests.sh
scripts/verify_agentic_app_tutorials.sh
```

安装到 AgenticOS 系统根目录：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
scripts/install_to_opt_agentic.sh
```

构建 ROS2 bridge package。该脚本面向部署工作区 `/home/ubuntu/agentic_ws`：

```bash
cd /home/ubuntu/agentic_ws/src/agentic_runtime_src
scripts/build_robot_bridge.sh
```

启动真实机器人入口示例：

```bash
/opt/agentic/bin/agentic --real --json "拍一张工作区照片"
/opt/agentic/bin/agentic photo --real --json "拍一张照片"
AGENTIC_LLM_ENABLED=1 AGENTIC_LLM_REQUIRE=1 \
  /opt/agentic/bin/agentic --real --json --require-llm "拍一张工作区照片"
```

真实机械臂运动需要显式授权：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
  /opt/agentic/bin/agentic --real --allow-arm-motion --yes --json \
  "从中间、左边、右边、上面拍照并验证差异"
```

---

## Native Agent App 开发

从模板创建新 App：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/create_agentic_app.py my_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
```

推荐阅读：

- `agentic_runtime_src/docs/agentic_app_developer_guide.md`
- `agentic_runtime_src/docs/tutorials/hello_world_agent.md`
- `agentic_runtime_src/docs/tutorials/color_block_grasper_agent.md`
- `agentic_runtime_src/docs/architecture.md`
- `agentic_runtime_src/docs/runtime_real_only.md`
- `agentic_runtime_src/docs/errors.md`

---

## 真实集成验证

真实依赖验证是显式 opt-in，不能用模拟成功替代：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
scripts/verify_real_ros2.sh
scripts/verify_real_llm.sh
scripts/verify_real_human.sh
```

默认未配置真实依赖时，验证脚本应返回 `UNVERIFIED_REAL_DEPENDENCY`，并给出下一步操作，而不是报告虚假的成功。

---

## 安全约定

- 不修改 `/opt/ros/*`、ROS2 upstream、Nav2 upstream、MoveIt upstream 或机器人厂商驱动源码。
- 不把 Agentic Runtime 放进 ROS2 作为普通业务 node。
- 不提交 `/opt/agentic/var`、真实照片、视频、审计日志、任务日志、运行输出或密钥。
- 不把 API key 写入源码、README、日志或测试快照。
- 不把 Gazebo / RViz-only / fake Nav2 路径写成真实机器人验收。
