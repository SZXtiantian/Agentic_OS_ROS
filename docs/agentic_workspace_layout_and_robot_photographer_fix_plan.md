# AgenticOS 工作区边界与 Robot Photographer 修复方案

生成时间：2026-06-15

本文整理当前 AgenticOS / Agent App / ROS2 Bridge 的目录边界，并给出 Robot Photographer 当前两个关键问题的修复方案：

1. Robot Photographer 的照片现在主要保存到 `/opt/agentic/var/evidence/photos`，缺少遵循 `app_template/storage` 形态的 App 侧用户产物目录。
2. `camera_pitch_down_15` 曾经错误映射到 `left_down.d6a`，导致“向下拍摄”表现成前伸/抓取类动作。

本文也解释：

- 为什么 `/home/ubuntu/agentic_ws/src` 里除了 `XXX_agent` 以外还有 runtime/source/template 等内容。
- `/home/ubuntu/agentic_ws/src/agentic_runtime_src` 每个目录的用途。
- 为什么源码里也有 `agentic_os`，而安装根在 `/opt/agentic`。
- `/home/ubuntu/agentic_ws/ros2_bridge_src` 是什么，为什么不是直接放到 `/opt/agentic`。

---

## 1. 当前目录角色总览

### 1.1 安装根：`/opt/agentic`

`/opt/agentic` 是已安装的 AgenticOS 系统根目录。它对应“运行时/系统侧”，类似一个产品安装目录。

主要内容：

```text
/opt/agentic
  bin/              operator CLI，例如 agentic、agenticctl
  lib/python3/      importable runtime Python 包，例如 agentic_runtime
  agentic_os/       AgenticOS kernel/source/ABI 层
  etc/              系统配置、bridge profile、本机 secrets
  skills/           已安装 capability/skill manifests
  bridges/          已安装 bridge 生命周期/元数据归属
  sdk/              SDK 输出物
  tests/            installed conformance tests
  docs/             installed 文档
  var/              运行时可变状态：audit、sessions、memory、storage、evidence
```

`/opt/agentic` 不应该作为日常开发源码目录。开发修改应发生在 `/home/ubuntu/agentic_ws/...`，然后通过安装脚本同步到 `/opt/agentic`。

### 1.2 Agent App 工作区：`/home/ubuntu/agentic_ws/src`

设计上，这个目录应该主要放 Agent Apps，例如：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent
/home/ubuntu/agentic_ws/src/inspection_agent
/home/ubuntu/agentic_ws/src/camera_arm_inspection_agent
```

但当前它还混放了：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src
/home/ubuntu/agentic_ws/src/app_template
```

这会造成认知混乱：用户看到 `src` 会以为里面都应该是 App，但现在 runtime source 也在里面。

当前可以理解为：

- `robot_photographer_agent` 等：真正的 Agent App package。
- `app_template`：App 脚手架模板，不是运行中的具体 App。
- `agentic_runtime_src`：AgenticOS Runtime/Kernel 的开发源码，不是 Agent App。

当前已做一次保守清理：

```text
/home/ubuntu/agentic_ws/archived_unused_apps_20260615/
  laundry_agent/
  pickup_agent/
  robotic_coding_agent/
  robotops_agent/
```

这些目录是早期 scaffold/sample agent，没有参与 `robot_photographer_agent` 的 planner、executor、SDK、bridge、policy 或测试链路，因此已经从 active `src` 工作区移走。

以下目录暂时保留：

```text
/home/ubuntu/agentic_ws/src/inspection_agent
/home/ubuntu/agentic_ws/src/camera_arm_inspection_agent
/home/ubuntu/agentic_ws/src/room_inspection_app
```

它们也不是 Robot Photographer 的业务依赖，但当前 Runtime 测试和历史文档仍引用它们：

- `inspection_agent`：Runtime/AppManager/kernel session 的早期代表 App。
- `camera_arm_inspection_agent`：真实相机和机械臂 allowlist 的早期验证 App。
- `room_inspection_app`：legacy room inspection 兼容测试。

后续如果要继续清理，需要先把 Runtime tests 从这些 legacy apps 迁移到 `robot_photographer_agent` 或专门的 minimal test app，然后再把它们归档。不能直接删除，否则 `scripts/run_tests.sh` 和 installed-side pytest 会失败。

建议后续重构成：

```text
/home/ubuntu/agentic_ws/apps/
  robot_photographer_agent/
  inspection_agent/
  ...

/home/ubuntu/agentic_ws/runtime_src/
  agentic_runtime_src/

/home/ubuntu/agentic_ws/app_templates/
  app_template/

/home/ubuntu/agentic_ws/ros2_bridge_src/
  agentic_msgs/
  agentic_capability_bridge/
  agentic_safety_guard/
  ...
```

短期可以保持当前路径不动，但必须在文档和命名上明确：`agentic_runtime_src` 不是 App。

### 1.3 ROS2 Bridge 源码工作区：`/home/ubuntu/agentic_ws/ros2_bridge_src`

这个目录是 AgenticOS-owned ROS2 bridge / HAL 的 colcon source workspace。

它不是 App 工作区，也不是 `/opt/agentic` 的安装根。

它存在的原因是：

- ROS2 package 需要 `package.xml`、`setup.py`、`CMakeLists.txt`、`msg/srv/action` 等 ROS2/colcon 结构。
- bridge package 可以 import `rclpy`，因为它们是 AgenticOS 的硬件/中间件适配层。
- Runtime/SDK/Agent Apps 不允许 import `rclpy`，也不能直接碰 ROS topic/service/action。
- `/opt/agentic` 保存安装结果、配置和运行状态，不适合作为 colcon source tree。

当前 bridge 源码包括：

```text
/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_msgs
/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_capability_bridge
/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_safety_guard
/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_world_model
/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_app_runtime_bridge
```

构建输出在：

```text
/home/ubuntu/agentic_ws/build/ros2_bridge
/home/ubuntu/agentic_ws/install/ros2_bridge
/home/ubuntu/agentic_ws/log/ros2_bridge
```

安装归属在：

```text
/opt/agentic/bridges/ros2
/opt/agentic/etc/bridge_profiles
```

也就是说：

```text
ros2_bridge_src = bridge 源码
agentic_ws/install/ros2_bridge = colcon build/install 输出
/opt/agentic/bridges/ros2 = AgenticOS 安装侧 bridge 归属和生命周期元数据
```

---

## 2. `/home/ubuntu/agentic_ws/src/agentic_runtime_src` 的用途

`agentic_runtime_src` 是 AgenticOS Runtime/Kernel 的开发源码树。它不是 Agent App。

它的职责是实现：

- CLI：`agentic`、`agenticctl` 背后的 Python runtime 命令。
- Runtime server/session/audit/syscall。
- Permission、resource lock、safety guard 调度。
- SDK high-level API。
- LLM provider。
- ROS bridge CLI client 和 mock client。
- Skill/capability registry。
- 安装到 `/opt/agentic` 的配置、skill manifests、docs、tests、scripts。

### 2.1 顶层文件

```text
AGENTS.md
```

项目开发约束和架构边界。强调：

- Agent Apps 不得 import `rclpy`。
- Runtime 不得 import `rclpy`。
- 只有 bridge packages 可以 import `rclpy`。
- 机器人运动必须经过 permission、resource lock、safety guard、audit。

```text
README.md
```

当前 AgenticOS for ROS2 的源码/安装布局说明。

```text
CODEX_IMPLEMENTATION_TASKBOOK.md
```

较长的实现任务书/历史任务记录。

```text
pyproject.toml
setup.py
setup.cfg
```

Python package 安装、测试、格式等配置。用于把 `agentic_runtime` 安装到 Python 环境或 `/opt/agentic/lib/python3`。

### 2.2 `agentic_runtime/`

这是 MVP Runtime 的可执行 Python 实现。安装后对应：

```text
/opt/agentic/lib/python3/agentic_runtime
```

重要子目录：

```text
agentic_runtime/app_factory
```

加载/校验 Agent App package。负责让 AIOS-compatible app 通过 manifest、entry class 等方式被 Runtime 加载。

```text
agentic_runtime/app_manager
```

App 管理逻辑，负责发现、注册、运行 App。

```text
agentic_runtime/config_manager
```

加载和刷新 Runtime 配置，例如 `/opt/agentic/etc/*.yaml`。

```text
agentic_runtime/context_manager
```

会话上下文管理，保存/恢复 App 运行上下文。

```text
agentic_runtime/execution_monitor
```

执行监控，记录任务执行状态、时间、失败信息等。

```text
agentic_runtime/hardware_adapter
```

AgenticOS hardware adapter 的管理层。这里不直接 import ROS，而是管理 bridge profile、transport、installer、bridge manager 等概念。

```text
agentic_runtime/kernel_service
```

Runtime kernel service 的服务层封装。

```text
agentic_runtime/llm
```

OpenAI-compatible LLM provider。当前支持从 `/opt/agentic/etc/models.yaml` 和 `/opt/agentic/etc/secrets/yunwu.env` 读取配置/密钥。

注意：LLM 只能参与 planner 输出 bounded JSON plan，不能直接控制 ROS 或实时运动。

```text
agentic_runtime/memory
```

Runtime memory manager 和 SQLite/in-memory provider。

```text
agentic_runtime/permission_manager
```

权限策略与 permission check。

```text
agentic_runtime/ros_bridge_client
```

Runtime 到 ROS2 bridge 的客户端层。

关键点：

- `cli_client.py` 通过 ROS2 CLI shell out 调用 bridge。
- 不 import `rclpy`。
- `mock_client.py` 用于测试/模拟。

```text
agentic_runtime/scheduler
```

任务/系统调用调度。当前以单机器人 FIFO 安全调度为主。

```text
agentic_runtime/sdk
```

Agent App 可调用的高层 SDK：

- `ctx.robot`
- `ctx.arm`
- `ctx.perception`
- `ctx.memory`
- `ctx.storage`
- `ctx.report`
- `ctx.world`
- `ctx.human`

App 应只调用 SDK，不直接碰 ROS。

```text
agentic_runtime/session
```

session store、session model、session manager。

```text
agentic_runtime/skill_executor
```

Skill/capability 执行链路：

```text
permission -> resource lock -> safety -> backend dispatch -> audit
```

这里是危险动作必须经过的核心路径。

```text
agentic_runtime/skill_registry
```

加载 `skills/*.yaml` capability manifest，做 schema 和 registry 管理。

```text
agentic_runtime/storage
```

Runtime storage manager。用于管理运行时 artifacts、recent photos 等。

```text
agentic_runtime/syscall
```

Runtime 侧 syscall model/store。

```text
agentic_runtime/tool_manager
```

普通 tool 管理。机器人能力不应该直接作为普通 tool 绕过 Runtime safety。

顶层 Python 文件：

```text
agentic_runtime/audit.py
```

审计日志写入和读取。

```text
agentic_runtime/cli.py
agentic_runtime/nl_cli.py
agentic_runtime/photo_cli.py
```

命令行入口。`/opt/agentic/bin/agentic photo` 最终调用 `photo_cli.py`。

```text
agentic_runtime/server.py
```

RuntimeServer，串起 session、skill execution、SDK context。

```text
agentic_runtime/types.py
```

通用类型、结果对象、ID 生成等。

### 2.3 `agentic_os/`

这是 AgenticOS kernel/source/ABI 层的源码副本，安装后对应：

```text
/opt/agentic/agentic_os
```

它不是第二个 `/opt/agentic`，也不是“另一个操作系统安装根”。它是 Python package 源码树。

为什么源码里也有 `agentic_os`？

因为开发流程是：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_os
  -> install_to_opt_agentic.sh
  -> /opt/agentic/agentic_os
```

也就是说：

```text
agentic_runtime_src/agentic_os = 开发源码
/opt/agentic/agentic_os = 安装结果
```

`agentic_os/` 下的子目录：

```text
agentic_os/kernel
```

AgenticOS kernel concept modules，移植 AIOS/Cerebrum 的内核思想，但适配机器人安全边界。

包括：

- `system_call`：Agentic system call 模型、executor。
- `capability`：capability/skill contract registry。
- `skill_library`：skill manifest registry。
- `memory`：kernel memory abstraction。
- `model_library`：模型 endpoint/router abstraction。
- `context`：context snapshot/recovery。
- `tool`：非机器人普通 tool 管理。
- `storage`：artifact-safe storage。
- `scheduler`：FIFO/round-robin scheduler。
- `perception`：perception frame normalization。
- `device_arbitration`：device/resource lease。
- `world_model`：place/world state resolver。

```text
agentic_os/hardware
```

硬件/中间件 adapter contract 文档。具体 ROS2 bridge 源码不在这里，而在 `ros2_bridge_src`。

```text
agentic_os/sdk
```

SDK 架构模块映射。当前 MVP SDK 实现主要在 `agentic_runtime/sdk`。

```text
agentic_os/security
```

安全层 taxonomy：

- `system_security`
- `model_security`
- `sensor_actuator_security`

当前多为 skeleton/contract，用来固定架构边界。

### 2.4 `configs/`

系统配置源文件，安装后对应：

```text
/opt/agentic/etc
```

主要文件：

```text
agentic.yaml
agentic_robot.yaml
runtime.yaml
permissions.yaml
safety.yaml
places.yaml
capabilities.yaml
models.yaml
bridge_profiles/
```

用途：

- `safety.yaml`：安全策略，例如 allowed named arm actions。
- `bridge_profiles/rosorin_arm_camera.yaml`：真实机器人 bridge backend 映射。
- `models.yaml`：LLM provider/model 配置。
- `places.yaml`：地点/world model。
- `permissions.yaml`：权限策略。
- `capabilities.yaml`：系统 capability 总表。

### 2.5 `skills/`

系统 capability/skill manifest 源文件，安装后对应：

```text
/opt/agentic/skills
```

例如：

```text
perception_capture_photo.yaml
arm_move_named.yaml
gripper_set.yaml
stop_robot.yaml
storage_list_recent_photos.yaml
```

这些是 Runtime/SDK 暴露给 Agent App 的能力 ABI。App 不能绕过它们直接碰 ROS。

### 2.6 `scripts/`

开发、安装、测试、真实机器人验收脚本。

重要脚本：

```text
install_to_opt_agentic.sh
```

把 source tree 同步安装到 `/opt/agentic`。

```text
run_tests.sh
check_forbidden_imports.py
check_filesystem_layout.py
```

测试和架构边界 guard。

```text
build_robot_bridge.sh
run_robot_bridge.sh
run_ros_bridge.sh
```

构建/启动 ROS2 bridge。

```text
real_robot_arm_health_gate.sh
real_robot_torque_semantics_probe.sh
real_robot_gripper_minimal_motion.sh
real_robot_arm_action_group_probe.sh
real_robot_multi_angle_photo_acceptance.sh
real_robot_arm_camera_acceptance.sh
```

真实机器人硬件健康门、动作组验证和验收脚本。

### 2.7 `docs/`

技术文档和任务书。

当前和 Robot Photographer 相关的关键文档：

```text
robot_photographer_agent_technical_design.md
robot_photographer_multi_angle_arm_plan.md
robot_arm_motion_recovery_solution.md
robot_arm_motion_recovery_execution_report.md
real_robot_deployment_taskbook.md
```

### 2.8 `tests/`

Runtime、SDK、layout、permission、bridge client、Robot Photographer integration 等测试。

这些测试用于保证：

- Runtime/SDK/App 不 import `rclpy`。
- App 不直接访问 ROS topics/actions/services。
- dangerous actions 经过 permission/resource/safety/audit。
- CLI 和 mock/real bridge client 行为符合预期。

---

## 3. 为什么 `agentic_ws` 里有很多不是 App 的东西

这是当前工程演进造成的混合布局。

最早为了快速开发，把这些都放进了一个 workspace：

```text
Agent Apps
Agentic Runtime source
AgenticOS kernel source
App template
ROS2 bridge source
colcon build/install/log outputs
```

所以你现在看到：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src
/home/ubuntu/agentic_ws/src/app_template
/home/ubuntu/agentic_ws/build
/home/ubuntu/agentic_ws/install
/home/ubuntu/agentic_ws/log
/home/ubuntu/agentic_ws/ros2_bridge_src
```

这不是最终最清晰的产品形态。

推荐目标布局：

```text
/opt/agentic
  installed AgenticOS root

/home/ubuntu/agentic_ws/apps
  Agent App source only

/home/ubuntu/agentic_ws/runtime_src
  Agentic Runtime / AgenticOS source only

/home/ubuntu/agentic_ws/ros2_bridge_src
  ROS2 bridge/HAL source only

/home/ubuntu/agentic_ws/templates
  App templates only
```

短期不建议立刻移动路径，因为当前脚本和安装器大量引用现有路径。应该先写清楚边界，再用一个专门 goal 做迁移。

---

## 4. Robot Photographer 问题一：照片保存位置不合理

### 4.1 当前行为

当前 `perception.capture_photo` 保存到：

```text
/opt/agentic/var/evidence/photos
```

这是 Runtime/OS 侧 evidence 目录。

它的合理性：

- 照片来自受控 system call。
- 保存过程要进入 audit。
- Runtime 要记录原始证据，避免 App 伪造硬件结果。
- App 不直接读 camera topic，不直接写 raw evidence。

问题：

- Robot Photographer 的用户产物不应该只放在 OS 全局 evidence 目录里。
- App 侧应该有自己的 run/output 目录。
- 用户要找“这个 App 拍的照片”时，不应该只去翻系统 evidence。

### 4.2 目标设计

正确设计不是把所有东西都塞进 `/opt/agentic/var/evidence/photos`，也不是让 App 直接绕过 Runtime 保存相机 topic。

应该分成两层：

1. OS/Runtime raw evidence：保存硬件 system call 返回的原始证据，用于审计、防伪、追责。
2. App storage：保存 Robot Photographer 面向用户的照片、视频、运行日志、索引、结果报告。

Robot Photographer 应该遵循 `app_template` 形态，补齐自己的应用目录：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/
  app.yaml
  config.json
  entry.py
  main.py
  planner.py
  validation.py
  verifier.py
  context/
  memory/
  models/
  prompts/
  policies/
  rules/
  schemas/
  skills/
  tools/
  workflows/
  tests/
  storage/
    photos/
    videos/
    logs/
    runs/
    indexes/
    tmp/
```

其中：

```text
/opt/agentic/var/evidence/photos/
```

只作为 Runtime raw evidence 目录，保存 `perception.capture_photo` 的原始 PNG、metadata、index.jsonl。

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/
```

才是 Robot Photographer App 侧用户产物目录。

单次运行建议目录：

```text
/opt/agentic/var/evidence/photos/
  raw runtime evidence
  immutable-ish audit evidence
  capture_photo 原始 PNG/metadata/index.jsonl

/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/runs/<session_id>/
  result.json
  photos/
    center.png
    yaw_left_15.png
    yaw_right_15.png
    pitch_up_15.png
  metadata/
    center.json
    yaw_left_15.json
    yaw_right_15.json
    pitch_up_15.json
  verification.json
  manifest.json
```

Runtime capture result 应同时返回：

```json
{
  "raw_evidence_image_path": "/opt/agentic/var/evidence/photos/...",
  "raw_evidence_metadata_path": "/opt/agentic/var/evidence/photos/...",
  "app_image_path": "/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/runs/<session_id>/photos/center.png",
  "app_metadata_path": "/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/runs/<session_id>/metadata/center.json",
  "audit_id": "audit_..."
}
```

App 顶层 `storage/photos` 可以保存稳定相册索引或 latest symlink/copy：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/photos/latest_center.png
/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/indexes/photos.jsonl
```

如果未来把 App 发布成安装包，Runtime 可以把这个 logical app storage mount 到：

```text
/opt/agentic/var/apps/robot_photographer_agent/storage
```

但在当前开发工作区，用户明确看到和管理的 App 侧 storage 应该是：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage
```

### 4.3 实现方案

1. Runtime 保持 `perception.capture_photo` 写 raw evidence。
2. Robot Photographer executor 在每个 capture step 成功后，把 raw evidence 复制或硬链接到 App `storage/runs/<session_id>/`。
3. App result 优先显示 `app_image_path`。
4. `storage.list_recent_photos` 支持按 App 过滤：

```text
storage.list_recent_photos(app_id="robot_photographer_agent")
```

5. Verification JSON 应写到 App run directory，同时保留 raw evidence 引用。
6. Audit log 记录 raw evidence path 和 app output path。
7. 不允许 App 直接从 ROS topic 保存照片；App 只能整理 Runtime 返回的 evidence。
8. `app.yaml` 应同时声明：

```yaml
evidence:
  root: /opt/agentic/var/evidence/photos
  role: runtime_raw_evidence

app_storage:
  root: storage
  runs: storage/runs
  photos: storage/photos
  videos: storage/videos
  logs: storage/logs
  indexes: storage/indexes
  tmp: storage/tmp
  role: app_owned_user_outputs
```

---

## 5. Robot Photographer 问题二：`pitch_down` 映射错误

### 5.1 事实

旧 session/audit 证明曾执行：

```text
camera_pitch_down_15 -> /home/ubuntu/software/arm_pc/ActionGroups/left_down.d6a
```

`left_down.d6a` 是 5 行动作组：

```text
(1, 1000, 843, 739, 82, 250, 500, 548)
(2, 1000, 844, 255, 153, 417, 501, 550)
(3, 1000, 844, 252, 151, 417, 501, 300)
(4, 1000, 844, 252, 151, 417, 501, 300)
(5, 1000, 844, 736, 79, 250, 500, 300)
```

按照 vendor `ActionGroupController` 逻辑，第 6 个 pulse 映射到 servo ID10 夹爪。

可以看到 ID10 从 `548/550` 变到 `300`，这不是纯相机 pitch-down 姿态，而是带末端/夹爪动作的前伸/抓取类序列。

### 5.2 根因

失败不是硬件没动，也不是照片没差异。

真正失败是语义映射错误：

```text
将“能产生差异的动作组”误认为“合法相机姿态”。
left_down.d6a 可运动、可拍出不同照片，但它不是 camera_pitch_down_15。
```

之前验证只证明了：

```text
left_down.d6a 真实运动
动作后能回 init
照片和其它角度不同
```

但没有证明：

```text
left_down.d6a 是纯 camera pitch down pose
```

这一步漏了，所以用户看到它像“往前抓东西”是正确观察。

### 5.3 当前安全状态

当前实时 `/agentic/arm/get_state` 显示 bridge 可用 camera pose 已经只有：

```text
camera_center
camera_yaw_left_15
camera_yaw_right_15
camera_pitch_up_15
```

`camera_pitch_down_15` 不应继续作为正式 bridge profile 的 available camera pose。

但 App 层仍需要同步清理：

- planner 不应生成 `camera_pitch_down_15`。
- schema 不应允许 `camera_pitch_down_15`。
- app.yaml/policy/prompt/tests 不应把它列为 allowed action。
- 如果用户要求“向下拍”，应返回 `CAMERA_POSE_BACKEND_MISSING` 或 `CAMERA_PITCH_DOWN_BACKEND_UNVERIFIED`，不能用 `left_down.d6a` 替代。

### 5.4 短期修复

将 Robot Photographer 正式多角度从 5 视角改成 4 视角：

```text
camera_center
camera_yaw_left_15
camera_yaw_right_15
camera_pitch_up_15
arm_home
```

移除：

```text
camera_pitch_down_15
```

需要修改：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/app.yaml
/home/ubuntu/agentic_ws/src/robot_photographer_agent/policies/robot_photographer.policy.yaml
/home/ubuntu/agentic_ws/src/robot_photographer_agent/schemas/photo_plan.schema.json
/home/ubuntu/agentic_ws/src/robot_photographer_agent/prompts/intent_parser.system.md
/home/ubuntu/agentic_ws/src/robot_photographer_agent/planner.py
/home/ubuntu/agentic_ws/src/robot_photographer_agent/validation.py
/home/ubuntu/agentic_ws/src/robot_photographer_agent/tests/*
/home/ubuntu/agentic_ws/src/agentic_runtime_src/configs/safety.yaml
/home/ubuntu/agentic_ws/src/agentic_runtime_src/configs/bridge_profiles/rosorin_arm_camera.yaml
/opt/agentic/etc/safety.yaml
/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml
```

同时更新 docs：

```text
robot_photographer_multi_angle_arm_plan.md
robot_photographer_agent_technical_design.md
robot_arm_motion_recovery_execution_report.md
```

### 5.5 中期修复：创建真正的 camera down pose

如果确实需要“向下拍”，应该创建新的 vendor action group，例如：

```text
/home/ubuntu/software/arm_pc/ActionGroups/camera_down.d6a
```

要求：

1. 不动夹爪 ID10，或 ID10 保持在安全固定值。
2. 不包含抓取/放置/伸手多段轨迹。
3. 不使用 `left_down/right_down/pick/place/grab` 这类语义不明动作组。
4. 尽量只改变相机视角相关关节。
5. 通过真实 position readback。
6. 通过图像人工审阅，确认是“相机下俯”，不是“机械臂前伸抓取”。
7. 通过静态动作组语义检查：

```text
rows <= 1 或人工标注 allow_multi_row_camera_pose=true
ID10 delta <= 20
动作组文件名不包含 pick/place/grab/down_left/right_down 等抓取倾向词
```

通过后再映射：

```yaml
camera_pitch_down_15:
  backend: servo_action_group
  backend_action: camera_down
  duration_s: 5
  description: Verified camera downward pitch pose. Does not operate gripper.
```

### 5.6 Verification 增强

图像差异 verification 不能只看：

```text
mean_abs_diff
hist_distance
phash_distance
changed_pixels_gt25_pct
```

还需要记录：

```json
{
  "pose_semantic_verified": true,
  "backend_action": "camera_up",
  "backend_action_group_semantics": "camera_pose",
  "gripper_delta": 0,
  "forbidden_motion_detected": false
}
```

也就是说：

```text
照片不同 != 姿态语义正确
```


## 7. 结论

当前系统不是一个纯 App workspace。它同时包含：

```text
Agent App source
Runtime source
AgenticOS kernel source
App template
ROS2 bridge source
colcon build/install/log artifacts
```

这在开发阶段可用，但对产品理解不友好。建议明确拆分逻辑：

```text
App 产物归 App
Runtime raw evidence 归 OS
ROS2 bridge 源码归 bridge workspace
/opt/agentic 只放安装结果和运行状态
```

Robot Photographer 当前最需要修的是：

```text
1. 用户照片输出目录从 OS evidence 中分离出 App run directory。
2. camera_pitch_down_15 不能再映射 left_down.d6a。
3. 多角度正式能力先降级为 4 角度，直到创建并验证真正的 camera_down.d6a。
```
