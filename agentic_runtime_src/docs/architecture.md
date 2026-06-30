# Architecture

## 项目目标

本项目是在 ROS2 之上的 Agentic OS / Agentic Runtime。它把机器人底层能力封装为 Agent App 可调用的高级系统 API，并为每次危险动作提供权限检查、资源锁、安全检查和审计日志。

核心目标：

- 让 Agent App 只调用任务级能力，而不是 ROS2 原始接口。
- 保持 Agentic Runtime 独立于 ROS2 Python client，不把 Runtime 做成普通 ROS2 node。
- 用 ROS2 Bridge package 适配现有 ROS2 topic、service、action、Nav2、MoveIt 和驱动。
- 所有机器人运动经过 Runtime permission check、resource lock、safety guard、audit log。

## 非目标

- 不修改 ROS2、Nav2、MoveIt 或机器人厂商驱动源码。
- 不修改 `/opt/ros/*`。
- 不让 LLM / Agent 做实时闭环控制。
- 不把 Agentic OS 做成一个普通 ROS2 业务节点。
- 不声明尚未接入真实 provider/backend 的复杂机械臂任务、App Store 或 VLM 深度推理为可用能力。

## 分层架构图

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime daemon/service wrapper
  -> AgenticOS Kernel (agentic_os.kernel)
  -> Robot Capability Layer
  -> ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

## 每层职责

- User：输入任务意图，例如“去厨房看看”。
- Agent App：编排任务级 API，不接触 ROS2 原始接口。
- Agentic SDK：提供 `ctx.robot`、`ctx.world`、`ctx.memory`、`ctx.human`、`ctx.report`。
- Agentic Runtime daemon/service wrapper：加载配置、暴露 CLI/daemon API、运行 App、维护 session/audit，并把核心 syscall、scheduler、memory、storage、context、tool、world model 能力转接到 kernel。
- AgenticOS Kernel：`agentic_os.kernel`，是 syscall、capability registry、scheduler、memory、storage、context、tool、skill registry、device arbitration、perception、model library、world model 的 source of truth。
- Robot Capability Layer：抽象 `navigate_to`、`inspect_area`、`stop_robot`、`get_robot_state` 等能力。
- ROS2 Bridge：唯一允许接触 `rclpy` 的 Agentic adapter 层，位于 `/home/ubuntu/agentic_ws/ros2_bridge_src/*`。
- Robot ROS2 Apps：机器人原本 ROS2 应用/功能包，位于 `/home/ubuntu/ros2_ws/src/*`，不放 Agentic 源码。
- ROS2：继续负责实时控制、Nav2、MoveIt、SLAM、传感器和驱动。
- Robot Hardware：真实或仿真的机器人。

## Runtime 进程模型

Foundation-complete Runtime 是普通 Python 进程，可以通过 CLI 启动：

```bash
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房
```

Runtime 进程负责加载配置、App manifest、Skill manifest、内存数据库和审计日志。Runtime 不 import `rclpy`，也不直接调用 ROS2 topic、service 或 action。

Runtime 中的 manager 应该优先作为 kernel-backed adapter 存在。例如：

- `agentic_runtime.memory.MemoryManager` 通过 `agentic_os.kernel.memory.MemoryManager` 执行 memory syscall。
- `agentic_runtime.skill_registry.SkillRegistry` 同步注册 `agentic_os.kernel.capability.CapabilityRegistry`，把 task API 映射成 runtime internal、ROS2 service/action、Nav2、MoveIt、perception 或 hardware-driver capability。
- `agentic_runtime.storage.StorageManager` 通过 `agentic_os.kernel.storage.StorageManager` 写 artifact。
- `agentic_runtime.context_manager.ContextManager` 通过 `agentic_os.kernel.context.ContextManager` snapshot/recover。
- `agentic_runtime.tool_manager.ToolManager` 通过 `agentic_os.kernel.tool.ToolManager` 执行通用工具并阻止 robot tool backdoor。
- `agentic_runtime.scheduler.SingleRobotScheduler` 使用 `agentic_os.kernel.scheduler.FIFORequestScheduler` 做单机器人调度准入。
- `agentic_os.kernel.scheduler.EnvironmentAwareDAGScheduler` 可通过
  `kernel.scheduler_policy: env_aware_priority_dag` 显式启用。它维护
  `TaskGraph` / `TaskNode` 全局 DAG、环境事实、资源租约、机会式融合、
  ACB 生命周期联动和 debug export，但 TaskNode dispatch 仍然通过
  `KernelService.execute_request(...)` 进入 typed syscall 和真实 Runtime
  能力路径。
- 未配置真实 bridge 时，place resolution 和机器人能力返回结构化错误，而不是生成成功结果。

## ROS2 Bridge 作用

ROS2 Bridge 是 Runtime 与 ROS2 之间的适配层。当前 foundation surface 包括：

- `agentic_world_model`：提供地点解析服务。
- `agentic_safety_guard`：提供安全检查和 stop service。
- `agentic_capability_bridge`：提供 state、inspection、navigation bridge。
- `agentic_app_runtime_bridge`：可选的聚合入口，当前保留 skeleton。

ROS2 Bridge 可以 import `rclpy`，但它不能绕过 Runtime 的安全模型对 Agent App 开放底层控制。

## Capability / HAL 模型

AgenticOS 对下不是直接暴露 ROS2 原始接口，而是维护一张 kernel capability table：

```text
Agent API / skill name
  -> capability kind: runtime_internal | ros2_service | ros2_action | nav2_action | moveit_action | perception | hardware_driver
  -> bridge interface: ROS2 service/action/topic name and type
  -> backend resource: Nav2 action, MoveIt action, perception backend, or vendor driver
  -> permissions, resource locks, safety constraints, audit requirements
```

例如 `robot.navigate_to` 是 task-level API，但在 kernel capability table 中被归类为 `nav2_action`，向下映射到 Agentic bridge action `/agentic/robot/navigate_to_place`，再由 bridge 隔离地接 Nav2 `/navigate_to_pose`。Agent App 和 Runtime 仍不 import `rclpy`。

## Agent App 禁止项

Agent App 禁止：

- import `rclpy`。
- publish `/cmd_vel`。
- 直接 subscribe `/scan`、`/odom`、`/tf`。
- 直接调用 Nav2 / MoveIt action。
- 生成实时速度、力矩、关节或底盘闭环控制指令。

Agent App 只允许调用 Agentic SDK 高级 API。

## Foundation API Surface

Foundation-complete runtime 声明以下 API surface：

- `ctx.robot.get_state()`
- `ctx.robot.navigate_to(place)`
- `ctx.robot.inspect_area(place)`
- `ctx.robot.stop()`
- `ctx.world.resolve_place(name)`
- `ctx.memory.remember(key, value)`
- `ctx.memory.recall(key)`
- `ctx.human.ask(question)`
- `ctx.report.say(message)`

第一个 Demo 是 room inspection：解析“厨房”，读取机器人状态，导航到厨房，检查区域，写入 memory，并向用户报告结果。

## Environment-Aware DAG Scheduler

The environment-aware scheduler is documented in
`docs/scheduler_environment_aware_dag.md`. Its ReadyQueue stores TaskNode IDs,
not ACB copies. Each TaskNode references an AgentControlBlock by `agent_id`;
syscall ownership and resource handles remain visible in the ACB lifecycle
tables.

The scheduler can reuse real environment facts such as `cup_pose` only when the
fact has TTL, confidence, schema, world epoch, syscall ID, audit ID, result
hash, and real dependency metadata. LLM planning output cannot create physical
world facts. If generic cup capabilities are absent, cup pickup verification
returns stable unavailable rather than substituting another capability.
