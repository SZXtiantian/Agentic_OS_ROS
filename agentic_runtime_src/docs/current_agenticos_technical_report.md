# 当前 AgenticOS 技术报告

生成时间：2026-06-14 17:40 CST  
更新：2026-06-16，Robot Photographer、自然语言 Dispatcher、`perception.capture_photo`、Runtime-owned `LLMChat` 和 required-LLM 验收路径已进入当前源码树。
主机角色：真实机器人部署环境  
报告范围：`/opt/agentic` 安装层、`/home/ubuntu/agentic_ws/src` Agent App 工作区、`/home/ubuntu/agentic_ws/ros2_bridge_src` AgenticOS ROS2 bridge/HAL 工作区。

## 1. 总体结论

当前 AgenticOS 已经不是一个单纯 demo 或 LLM wrapper，而是形成了一个可安装、可测试、带安全边界的机器人运行时雏形。

已经具备：

- `/opt/agentic` 作为安装后的 AgenticOS root。
- Runtime / SDK / Agent App 与 ROS2 bridge 分层隔离。
- Runtime 和 Agent App 不 import `rclpy`。
- 只有 `/home/ubuntu/agentic_ws/ros2_bridge_src/*` 下的 bridge packages 接触 ROS2。
- 已有权限检查、资源锁、安全检查、审计日志、session 记录、SQLite memory、skill manifest。
- 已有真实机器人 camera + manipulator bridge profile。
- 已发现真实相机 topic `/depth_cam/rgb0/image_raw` 和机械臂 `/servo_controller`。
- 已实现 `camera_arm_inspection_agent`，可以通过 AgenticOS 读取真实相机 metadata，并在环境变量允许时调用 allowlist 中的机械臂动作。
- 已实现 `robot_photographer_agent` 的 AIOS-compatible App package、plan-first executor、schema/policy tests、四姿态多角度拍摄计划和照片差异验证。
- 已新增自然语言 Dispatcher 路由到 `robot_photographer_agent`，并支持 `--require-llm` / `AGENTIC_LLM_REQUIRE=1` 禁止 required-LLM 验收回退到 rule-based。
- 已新增 Runtime-owned `LLMChat` facade；Agent Apps 只使用注入的 `llm_chat`，不构造 provider client、不读取模型配置或 API key。

当前仍需注意：

- 默认 `/opt/agentic/etc/agentic.yaml` 中 `ros_bridge_mode` 已收敛为 `cli`；真实 bridge 缺失时必须 fail-fast。
- 真实 LLM 验收仍需要本机 `/opt/agentic/etc/secrets/yunwu.env` 或环境变量提供 API key，且不能把 secret 写入源码、文档或日志。
- 自然语言入口以 `/opt/agentic/bin/agentic` 为主，`agentic photo` 保留为兼容/调试入口。
- `perception.capture_photo` 已作为正式能力进入 Runtime/SDK/bridge/client 路径；真实执行仍依赖 bridge services 正常启动。
- 真实 bridge services 需要启动 `/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_bridge.sh` 后才会出现在 ROS graph。

## 2. AgenticOS 的定位

AgenticOS 运行在 ROS2 之上，但不是 ROS2 fork，也不是普通 ROS2 业务节点。它的目标是把机器人底层能力封装成 Agent App 可以调用的高级、安全、可审计 capability。

目标分层：

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Robot Capability Layer
  -> AgenticOS Hardware Adapter / ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

关键原则：

- Agent App 只表达任务意图。
- Runtime 负责权限、安全、资源、session、audit。
- ROS2 bridge 是 AgenticOS-owned HAL / driver adapter。
- ROS2 继续负责传感器、控制器、Nav2、MoveIt、vendor driver 和实时控制。
- LLM / Agent 逻辑不能做实时闭环控制。

## 3. 文件系统与所有权

当前主要目录：

```text
/opt/agentic
/home/ubuntu/agentic_ws/src
/home/ubuntu/agentic_ws/ros2_bridge_src
/home/ubuntu/ros2_ws/src
```

### 3.1 `/opt/agentic`

`/opt/agentic` 是安装后的 AgenticOS root，不是开发 workspace。

当前主要内容：

```text
/opt/agentic/bin
/opt/agentic/lib/python3/agentic_runtime
/opt/agentic/agentic_os
/opt/agentic/etc
/opt/agentic/skills
/opt/agentic/docs
/opt/agentic/tests
/opt/agentic/var
```

含义：

- `bin/`：薄 CLI wrapper，例如 `agentic`、`agenticctl`、`agentic-run`、`agentic-app`、`agenticd`。
- `lib/python3/agentic_runtime/`：可执行 Runtime / SDK / CLI / service wrapper。
- `agentic_os/`：AgenticOS kernel source、ABI map、architecture taxonomy。
- `etc/`：系统配置、权限、安全、模型、bridge profile。
- `skills/`：capability / skill manifest。
- `docs/`：安装层文档。
- `tests/`：安装层 conformance tests。
- `var/`：可变运行状态，包括 audit、session、memory、evidence、storage、context。

### 3.2 `/home/ubuntu/agentic_ws/src`

这是 Agent App workspace 和 Runtime 源码 workspace。

当前 app / source：

```text
agentic_runtime_src
app_template
camera_arm_inspection_agent
inspection_agent
laundry_agent
pickup_agent
robotic_coding_agent
robotops_agent
room_inspection_app
```

`agentic_runtime_src` 是当前 Runtime 源码 source of truth。安装到 `/opt/agentic` 由：

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh
```

完成。

### 3.3 `/home/ubuntu/agentic_ws/ros2_bridge_src`

这是 AgenticOS-owned ROS2 bridge/HAL source workspace。允许 import `rclpy` 的 AgenticOS 代码只应该在这里。

当前 packages：

```text
agentic_msgs
agentic_app_runtime_bridge
agentic_capability_bridge
agentic_safety_guard
agentic_world_model
```

这些包已通过 colcon build。

### 3.4 `/home/ubuntu/ros2_ws/src`

这是机器人原本 ROS2 应用 / vendor / driver workspace。AgenticOS Runtime 和 Agent App 不放在这里，也不修改这里的 vendor driver source。

## 4. Runtime / Kernel 当前状态

Runtime 源码位于：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime
```

安装后位于：

```text
/opt/agentic/lib/python3/agentic_runtime
```

当前主要模块：

```text
agentic_runtime/cli.py
agentic_runtime/nl_cli.py
agentic_runtime/server.py
agentic_runtime/audit.py
agentic_runtime/config.py
agentic_runtime/sdk/
agentic_runtime/session/
agentic_runtime/memory/
agentic_runtime/storage/
agentic_runtime/syscall/
agentic_runtime/scheduler/
agentic_runtime/skill_executor/
agentic_runtime/skill_registry/
agentic_runtime/permission_manager/
agentic_runtime/ros_bridge_client/
agentic_runtime/hardware_adapter/
agentic_runtime/kernel_service/
agentic_runtime/app_factory/
```

Kernel source 位于：

```text
/opt/agentic/agentic_os/kernel
```

当前 kernel 模块：

```text
capability
context
device_arbitration
memory
model_library
perception
scheduler
skill_library
storage
system_call
tool
world_model
```

Runtime 当前提供：

- CLI / daemon-style entrypoints。
- App manifest 加载与校验。
- Skill registry。
- Permission manager。
- Resource manager。
- Safety check 调用。
- Audit logger。
- Session manager。
- SQLite memory provider。
- Storage / context / syscall / scheduler adapter。
- Mock bridge client 与 ROS2 CLI bridge client。

## 5. SDK 与高层 API

Agent App 通过 `AgentContext` 调用高层 API，不直接调用 ROS2。

当前 MVP / 已扩展 API：

```text
ctx.robot.get_state()
ctx.robot.navigate_to(place)
ctx.robot.inspect_area(place)
ctx.robot.stop()
ctx.world.resolve_place(name)
ctx.memory.remember(key, value)
ctx.memory.recall(key)
ctx.human.ask(question)
ctx.report.say(message)
ctx.perception.observe(target)
ctx.arm.get_state()
ctx.arm.move_named(name)
ctx.gripper.open()
ctx.gripper.close_low_force()
```

当前安装的 skills：

```text
arm.get_state
arm.move_named
gripper.set
human.ask
memory.recall
memory.remember
perception.observe
report.say
robot.get_state
robot.inspect_area
robot.navigate_to
robot.stop
world.resolve_place
```

待实现的摄影应用关键新增能力：

```text
perception.capture_photo
```

它应保存真实 PNG / metadata，而不是只返回 camera metadata。

## 6. ROS2 Bridge / HAL 当前状态

bridge source：

```text
/home/ubuntu/agentic_ws/ros2_bridge_src
```

build 命令：

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/build_robot_bridge.sh
```

最近 build 结果：

```text
Summary: 5 packages finished
AgenticOS real-robot bridge packages built.
```

当前 bridge packages：

### 6.1 `agentic_msgs`

定义 AgenticOS 与 ROS2 bridge 之间的 msg / srv / action contract。

当前包括：

```text
action/ExecuteSkill.action
action/MoveArmNamed.action
action/NavigateToPlace.action
msg/ArmState.msg
msg/Place.msg
msg/RobotState.msg
msg/SafetyState.msg
msg/SkillDescription.msg
msg/Task.msg
msg/WorldObject.msg
srv/AskHuman.srv
srv/CheckSafety.srv
srv/GetArmState.srv
srv/GetRobotState.srv
srv/InspectArea.srv
srv/Observe.srv
srv/ResolvePlace.srv
srv/SetGripper.srv
srv/StopRobot.srv
```

摄影应用下一步需要新增：

```text
srv/CapturePhoto.srv
```

### 6.2 `agentic_capability_bridge`

当前包含：

```text
state_bridge_node.py
inspection_bridge_node.py
navigation_bridge_node.py
manipulation_bridge_node.py
```

职责：

- `state_bridge_node.py`：提供 `/agentic/robot/get_state`。
- `inspection_bridge_node.py`：订阅相机 topic，提供 `/agentic/perception/observe` 和 `/agentic/perception/inspect_area`。
- `navigation_bridge_node.py`：当前主要是 mock / bridge 层导航能力，不应被 Agent App 直接绕过。
- `manipulation_bridge_node.py`：提供 `/agentic/arm/move_named`、`/agentic/arm/get_state`、`/agentic/gripper/set`、`/agentic/arm/stop`。

### 6.3 `agentic_safety_guard`

提供：

```text
/agentic/safety/check
/agentic/robot/stop
```

当前会检查：

- estop parameter。
- forbidden zones。
- camera target allowlist。
- observe / inspect timeout。
- arm named action allowlist。
- arm timeout。
- gripper command / force allowlist。
- gripper range。
- stop 时转发到 `/agentic/arm/stop`。

### 6.4 `agentic_world_model`

提供地点解析能力，给 `ctx.world.resolve_place(name)` 使用。

### 6.5 `agentic_app_runtime_bridge`

当前是 MVP skeleton / bridge 聚合入口，保留作为后续 Runtime 与 ROS2 更紧密集成的扩展点。

## 7. 真实机器人接入现状

真实机器人 bridge profile：

```text
/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml
```

关键配置：

```text
profile_name: rosorin_arm_camera
robot_id: rosorin_real_robot
ros_domain_id: 0
primary_rgb_topic: /depth_cam/rgb0/image_raw
camera frame: rgb_camera_link
arm backend_type: servo_action_group
arm action topic: /servo_controller
action_group_path: /home/ubuntu/software/arm_pc/ActionGroups
```

已发现真实 ROS graph 中的关键 topic：

```text
/depth_cam/depth0/camera_info
/depth_cam/depth0/image_raw
/depth_cam/depth0/points
/depth_cam/ir0/image_raw
/depth_cam/rgb0/camera_info
/depth_cam/rgb0/image_raw
/servo_controller
```

允许的机械臂动作：

```text
arm_home  -> /home/ubuntu/software/arm_pc/ActionGroups/init.d6a
camera_up -> /home/ubuntu/software/arm_pc/ActionGroups/camera_up.d6a
```

允许的夹爪动作：

```text
open_gripper
close_gripper_low_force
```

stop 后端：

```text
ActionGroupController.stop_action_group
```

当前真实感知状态：

- `perception.observe` 能从 `/depth_cam/rgb0/image_raw` 获取 fresh frame metadata。
- evidence 下已有真实相机 metadata 文件。
- evidence 下已有一张手动保存的真实相机 PNG：

```text
/opt/agentic/var/evidence/manual_depth_cam_rgb0_20260614_021644.png
```

当前不足：

- 真实拍照仍依赖 bridge services 和相机 topic 在线。
- required-LLM 验收必须显式设置 `--require-llm` 或 `AGENTIC_LLM_REQUIRE=1`。
- `camera_pitch_down_15` 暂不开放，不能映射到 `left_down.d6a` 或其他未验证动作组。

## 8. Agent App 当前状态

当前 app 列表：

```text
app_template
camera_arm_inspection_agent
inspection_agent
robot_photographer_agent
room_inspection_app
```

### 8.1 `inspection_agent`

功能：

- 解析地点。
- 检查地点是否 forbidden。
- 获取机器人状态。
- 调用 `ctx.robot.navigate_to(place)`。
- 调用 `ctx.robot.inspect_area(place)`。
- 写 memory。
- 向用户 report。

安全行为：

- 导航失败时询问用户是否重试。
- safety rejected / timeout / unexpected error 时调用 stop。

当前导航和 inspect 在默认配置下主要走 mock bridge。

### 8.2 `camera_arm_inspection_agent`

功能：

- 获取 robot state。
- 获取 arm state。
- 调用 `ctx.perception.observe(target)`。
- 默认只读观察。
- 只有 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` 或显式 `move_arm=True` 时，才执行 allowlist 中的 arm action。
- 当前默认 arm action 是 `camera_up`。
- 动作后执行低风险 gripper open。
- 错误时尝试 `ctx.robot.stop()` 并返回 stop evidence。

这个 app 是真实机器人 camera + manipulator demo 的当前代表应用，但它仍是 inspection demo，不是最终摄影应用。

### 8.3 `robot_photographer_agent`

已实现为当前代表性的真实机器人摄影 Agent App：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent
/home/ubuntu/agentic_ws/src/agentic_runtime_src/docs/robot_photographer_agent_technical_design.md
```

当前支持：

- `/opt/agentic/bin/agentic --real --json "拍一张工作区照片"`
- required-LLM 验收：`AGENTIC_LLM_ENABLED=1 AGENTIC_LLM_REQUIRE=1 /opt/agentic/bin/agentic --real --json --require-llm "拍一张工作区照片"`
- 单张拍照
- `camera_pitch_up_15` 后拍照
- `arm_home`
- 连拍
- 前后对比拍照
- 最近照片
- 状态
- 停止
- Runtime-owned LLMChat + rule-based fallback
- `perception.capture_photo`
- 四姿态多角度拍摄：center / yaw_left / yaw_right / pitch_up
- deterministic image-difference verification

## 9. CLI 当前状态

当前安装的 operator commands：

```text
/opt/agentic/bin/agentic
/opt/agentic/bin/agenticctl
/opt/agentic/bin/agentic-run
/opt/agentic/bin/agentic-app
/opt/agentic/bin/agenticd
```

`agentic` wrapper 当前支持：

```text
agentic enter
agentic env
agentic chat
agentic shell
agentic <runtime-cli-subcommand>
```

`agentic enter` 会进入 AgenticOS 环境 shell。

`agentic chat --real` 会进入自然语言 CLI。当前支持：

```text
看一下工作区
拍一张 workspace 的照片
查看状态
最近会话
最近审计
停止机器人
退出
```

当前自然语言 CLI 的实现位于：

```text
/opt/agentic/lib/python3/agentic_runtime/nl_cli.py
```

它目前是规则解析：

- 识别 help / status / sessions / audit / stop。
- 识别拍照、图像、相机、看一下等词，映射到 `camera_arm_inspection_agent`。
- 识别抬起、机械臂等词后，会尝试机械臂动作；如果没有运动权限，则降级为只读观察。
- `--real` 模式下会自动尝试启动 AgenticOS ROS bridge。

当前还没有：

```text
agentic photo
```

它应在 `robot_photographer_agent` 阶段实现。

## 10. 模型 / LLM 当前状态

当前模型配置：

```yaml
models:
  default_reasoning_model:
    provider: mock
    enabled: false
  edge_lora_root: /opt/agentic/agentic_os/kernel/model_library
```

结论：

- 当前没有真实 LLM provider 接入。
- 当前 `agentic chat` 不是 LLM chat，而是规则型 natural language CLI。
- `llm_planning_enabled` 在现有 app manifest 中为 `false`。
- 后续摄影应用可以添加 LLM intent-parser abstraction，但必须保留 rule-based fallback。
- LLM 只能输出受限 JSON plan，不能直接控制 ROS2 或实时机器人动作。

## 11. 安全、权限、资源锁与审计

当前 safety 配置：

```text
require_permission_check: true
require_resource_lock: true
require_safety_guard: true
require_audit_log: true
```

已配置权限：

```text
robot.state.read
robot.move
robot.stop
world.read
perception.inspect
perception.observe
arm.state.read
arm.move.named
gripper.control
memory.read
memory.write
human.ask
report.say
```

已配置 safety 规则：

- forbidden zones：`stairs`、`elevator`、`lab_restricted_zone`。
- camera allowed targets：`workspace`、`arm_workspace`、`desk`。
- camera max observe duration：`60s`。
- manipulation max arm duration：`8s`。
- allowed named arm actions：`arm_home`、`camera_up`。
- allowed gripper commands：`open`、`close`。
- allowed gripper force：`low`。
- workspace bounds 和 gripper pulse limits。

资源锁当前至少覆盖：

- base / navigation。
- camera / perception。
- arm。
- gripper。

Audit 当前写入：

```text
/opt/agentic/var/audit/audit.jsonl
```

Audit 记录包含：

- `app_id`
- `session_id`
- `skill_name`
- `args`
- `backend`
- `permission_result`
- `resource_lock_result`
- `safety_result`
- `status`
- `error_code`
- `duration_ms`
- `result`

最近 audit 显示系统能够记录 skill success、backend 类型、resource lock 和 safety result。

## 12. Session、Memory、Evidence

Session root：

```text
/opt/agentic/var/sessions
```

最近 session 示例：

```text
inspection_agent completed
camera_arm_inspection_agent completed
camera_arm_inspection_agent failed
```

Memory DB：

```text
/opt/agentic/var/memory/memory.sqlite3
```

Evidence root：

```text
/opt/agentic/var/evidence
```

当前 evidence 示例：

```text
acceptance_observe_camera_metadata.json
manual_depth_cam_rgb0_20260614_021644.json
manual_depth_cam_rgb0_20260614_021644.png
observe_*_camera_metadata.json
```

摄影应用应改用：

```text
/opt/agentic/var/evidence/photos
```

并保存：

```text
photo_*.png
photo_*.json
index.jsonl
shot_set_*.json
comparison_*.json
```

## 13. 当前运行状态

`agenticctl status` 当前摘要：

```text
agenticd: running
ros_bridge: mock
scheduler: single_robot_fifo
skills: ready
resource_locks:
  - base: free
```

注意：

- `ros_bridge: mock` 表示默认 Runtime 配置仍是 mock。
- 真实机器人 bridge 可以通过脚本启动：

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_bridge.sh
```

ROS graph 查询时观察到真实硬件相关 topic：

```text
/depth_cam/rgb0/image_raw
/depth_cam/rgb0/camera_info
/depth_cam/depth0/image_raw
/depth_cam/depth0/points
/servo_controller
```

查询时未看到 `/agentic/...` services，说明当时 AgenticOS ROS bridge service 进程未常驻运行，或未在该 shell 的 ROS environment 中可见。

## 14. 已通过的验证

### 14.1 Runtime / Static Guard

命令：

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_tests.sh
```

结果：

```text
forbidden import/static guard ok
filesystem layout guard ok
80 passed
Agentic OS MVP checks passed.
```

### 14.2 Bridge Build

命令：

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/build_robot_bridge.sh
```

结果：

```text
Summary: 5 packages finished
AgenticOS real-robot bridge packages built.
```

### 14.3 CLI 查询

命令：

```bash
agentic apps
agentic skills
agentic sessions --limit 5
agentic audit --limit 5
agenticctl status
```

结果：

- app registry 可列出 8 个 apps。
- skill registry 可列出 13 个 skills。
- session / audit 查询可用。
- status 查询可用。

## 15. 已知问题与风险

### 15.1 默认 bridge mode 为真实 CLI bridge

`/opt/agentic/etc/agentic.yaml` 当前：

```yaml
ros_bridge_mode: cli
```

缺少 ROS2、bridge service 或 robot/Nav2 后端时，Runtime 必须返回稳定错误码（例如 `ROS_BRIDGE_UNAVAILABLE`），不能用模拟成功路径替代真实执行。

### 15.2 setup.bash 有 ROS overlay warning

执行 `source /opt/agentic/setup.bash` 时，当前环境出现过：

```text
/opt/ros/humble/setup.bash: no such file or directory: /home/ubuntu/setup.sh
/opt/ros/humble/local_setup.bash: no such file or directory: /home/ubuntu/local_setup.sh
```

这可能来自 ROS overlay / shell 环境污染。当前不影响 `agenticctl status` 和 tests，但建议后续清理环境加载链。

### 15.3 真实拍照能力尚未产品化

当前相机 bridge 能读 frame metadata，但正式摄影应用需要：

- `CapturePhoto.srv`
- `/agentic/perception/capture_photo`
- PNG 保存
- metadata 保存
- photos index
- SDK `ctx.perception.capture_photo()`
- `agentic photo` CLI

### 15.4 LLM 尚未接入

当前模型为 disabled mock。摄影应用需要先设计 provider abstraction，保留 rule-based fallback，再接真实 LLM。

### 15.5 Navigation 仍不是本阶段重点

当前真实机器人任务优先是 camera + manipulator。不要为了 demo 添加 Gazebo/gz/fake Nav2/RViz-only 内容。

### 15.6 运动安全仍需真实硬件回归

当前 allowlist 机械臂动作为：

```text
arm_home
camera_up
```

但每次真实运动前仍应确认：

- action group 文件存在。
- `/servo_controller` 有订阅者。
- stop backend 可用。
- 工作空间无人手干涉。
- 环境变量 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` 明确设置。

## 16. 建议的下一步

优先级 1：完成 Robot Photographer required-LLM 和真实机器人验收闭环。

参考文档：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/docs/robot_photographer_agent_technical_design.md
```

核心目标：

- 运行 required-LLM 验收，确认 Dispatcher 和 App planner 都是 `planner_mode=llm`。
- 确认 LLM 失败时返回 `DISPATCH_LLM_REQUIRED_FAILED` 或 `ROBOT_PHOTOGRAPHER_LLM_REQUIRED_FAILED`，不接受 rule fallback。
- 运行真实只读拍照验收，确认 PNG、metadata、audit、session、storage index 全链路存在。
- 在 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` 和 `--allow-arm-motion --yes` 下验证四姿态多角度拍摄。
- 保持 `camera_pitch_down_15` 未开放，直到有独立安全后端和图像证据。

优先级 2：清理启动环境 warning。

检查 `/opt/agentic/setup.bash`、ROS overlay、shell 启动脚本，避免错误引用 `/home/ubuntu/setup.sh` 和 `/home/ubuntu/local_setup.sh`。

优先级 3：真实 bridge lifecycle 管理。

把 `/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_bridge.sh` 纳入更明确的 AgenticOS bridge lifecycle：启动、状态、日志、停止、profile 检查。

优先级 4：模型 provider。

在不破坏安全边界的前提下添加真实 LLM provider：

- LLM 只做 intent parsing。
- 输出必须是 bounded JSON plan。
- Runtime 必须重新校验 plan。
- LLM 不可直接调用 ROS2。

优先级 5：真实 acceptance 脚本扩展。

更新：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_camera_acceptance.sh
```

加入：

- read-only photo capture。
- optional `camera_up + capture`。
- stop/cancel evidence。
- latest sessions/audit 校验。

## 17. 本报告生成时执行过的命令

```bash
ls -la /opt/agentic /opt/agentic/bin /opt/agentic/docs /opt/agentic/etc
find /home/ubuntu/agentic_ws/src/agentic_runtime_src -maxdepth 3 -type f
find /home/ubuntu/agentic_ws/ros2_bridge_src -maxdepth 4 -type f
agenticctl status
agentic --help
agentic apps
agentic skills
agentic sessions --limit 5
agentic audit --limit 5
ros2 topic list
ros2 service list
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/build_robot_bridge.sh
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_tests.sh
```

有一个额外的 Python 探查命令尝试访问 `RuntimeServer.app_manager`，该属性不存在，因此该探查失败。它没有修改系统，也不影响本报告结论。

## 18. 简短判断

当前 AgenticOS 已经具备“操作系统式机器人能力层”的骨架：安装根目录清晰、Runtime 与 ROS2 bridge 分离、Agent App 只能走 SDK、危险动作有权限/安全/资源/审计路径、真实相机与机械臂 profile 已接入。

现在最有价值的下一步不是继续横向堆 demo，而是按 `robot_photographer_agent_technical_design.md` 做一个真正纵向闭环的摄影应用：从自然语言到 plan，到安全校验，到机械臂 allowlist 动作，到真实相机保存图片，到 session/audit/evidence 全链路闭合。
