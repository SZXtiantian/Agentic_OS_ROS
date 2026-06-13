# Agentic OS for ROS2 — Codex 工程实施任务书

> 当前布局更新：本任务书早期版本把 Agentic ROS2 bridge package 放在 `ros2_ws/src/agentic_*`。该布局已被部署目录重构取代。  
> 当前准则是：`/home/ubuntu/ros2_ws/src` 只放机器人 ROS2 应用/功能包；Agentic Runtime、Agent Apps、Agentic 自带 ROS2 bridge 都归属 `/home/ubuntu/agentic_ws`。  
> Agentic ROS2 bridge 当前源码路径为 `/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_*`，单独用 colcon build 到 `/home/ubuntu/agentic_ws/install/ros2_bridge`。  
> 当前安装层为 `/opt/agentic`。请以 `/opt/agentic/docs/module_mapping.md` 和 `/home/ubuntu/agentic_ws/src/agentic_runtime_src/docs/module_mapping.md` 为准。

> 文件用途：本文件用于指导 Codex 在仓库中逐步实现 ROS2 之上的 Agentic OS / Agentic Runtime MVP。  
> 使用方式：把本文放到仓库根目录，建议文件名为 `CODEX_IMPLEMENTATION_TASKBOOK.md`。同时根据本文第 3 节生成或更新仓库根目录的 `AGENTS.md`，让 Codex 每次进入仓库时先读取项目约束。  
> 当前版本：v0.1  
> 日期：2026-06-12  
> 执行原则：先完成最小闭环，再扩展复杂能力。不要一开始重构成“大而全平台”。

---

## 0. Codex 执行总规则

Codex 在执行本文任何任务前，必须遵守以下规则。

### 0.1 先读后改

每次任务开始前先执行：

```bash
pwd
find . -maxdepth 3 -type f | sort | sed 's#^\./##' | head -200
```

如果仓库已有文件，必须先阅读相关文件：

```bash
sed -n '1,220p' README.md 2>/dev/null || true
sed -n '1,220p' AGENTS.md 2>/dev/null || true
find . -name "pyproject.toml" -o -name "package.xml" -o -name "setup.py" -o -name "CMakeLists.txt" | sort
```

禁止在不了解现有结构的情况下直接大面积覆盖文件。

### 0.2 小步提交

每个任务只完成一个明确目标。不要在一个任务里同时实现 ROS2 bridge、Runtime、SDK、App、CI。

推荐提交粒度：

```text
T0.1 repo skeleton
T1.1 agentic_msgs
T1.2 world_model_node
T2.1 runtime core schemas
T3.1 room_inspection_app
```

每个任务完成后，必须输出：

```text
变更文件列表
执行过的命令
测试结果
未完成事项
下一步建议
```

### 0.3 不允许修改 ROS2 源码

禁止修改：

```text
/opt/ros/*
ROS2 upstream source
Nav2 upstream source
MoveIt upstream source
robot vendor driver source
```

允许新增：

```text
ros2_ws/src/agentic_msgs
ros2_ws/src/agentic_capability_bridge
ros2_ws/src/agentic_safety_guard
ros2_ws/src/agentic_world_model
ros2_ws/src/agentic_app_runtime_bridge
agentic_runtime
agentic_apps
configs
docs
scripts
tests
```

### 0.4 Agent App 不允许直接接触 ROS2

Agent App 代码中禁止出现：

```text
import rclpy
from rclpy
/cmd_vel
/scan
/odom
/tf
NavigateToPose
MoveGroup
ActionClient
create_publisher
create_subscription
```

Agent App 只能使用：

```python
await ctx.robot.get_state()
await ctx.robot.navigate_to(place)
await ctx.robot.inspect_area(place)
await ctx.robot.stop()

await ctx.world.resolve_place(name)

await ctx.memory.remember(key, value)
await ctx.memory.recall(key)

await ctx.human.ask(question)
await ctx.report.say(message)
```

### 0.5 LLM / Agent 不允许做实时闭环控制

禁止设计：

```text
LLM 输出速度指令
LLM 长期发布 /cmd_vel
LLM 高频处理 /scan
LLM 直接读 /odom 做闭环
LLM 直接绕过 safety_guard 控制机械臂
```

正确设计：

```text
LLM / Agent 只能选择任务级 skill。
实时控制继续由 ROS2 controller / Nav2 / MoveIt 负责。
所有运动能力必须经过 Runtime permission + safety_guard。
```

---

## 1. 项目目标

本项目不是普通 ROS2 package，不是简单 LLM wrapper，也不是修改 ROS2 源码。

本项目要实现：

```text
一套运行在 Ubuntu + ROS2 之上的 Agentic OS / Agentic Runtime。
它把 ROS2 的底层机器人能力封装为 Agent 可调用、App 可开发、权限可管理、安全可约束、执行可审计的高级系统 API。
```

目标架构：

```text
User / Human Command
  ↓
Agent App
  ↓
Agentic API / SDK
  ↓
Agentic Runtime / Kernel
  - App Manager
  - Intent Manager
  - Task Planner
  - Permission Manager
  - Skill Registry
  - Skill Executor
  - Safety Manager
  - Execution Monitor
  - World Model Client
  - Memory Manager
  - Audit Logger
  ↓
Robot Capability Layer
  - navigate_to
  - inspect_area
  - find_object
  - pick_object
  - place_object
  - stop_robot
  - get_robot_state
  ↓
ROS2 Bridge / Adapter Layer
  - navigation_bridge_node
  - perception_bridge_node
  - manipulation_bridge_node
  - state_bridge_node
  - safety_guard_node
  - world_model_node
  ↓
ROS2
  - topic
  - service
  - action
  - Nav2
  - MoveIt
  - SLAM
  - Perception
  - robot drivers
  ↓
Robot Hardware
```

---

## 2. MVP 范围

### 2.1 MVP 必须支持

MVP 必须支持以下高级 API：

```python
await ctx.robot.get_state()
await ctx.robot.navigate_to(place)
await ctx.robot.inspect_area(place)
await ctx.robot.stop()

await ctx.world.resolve_place(name)

await ctx.memory.remember(key, value)
await ctx.memory.recall(key)

await ctx.human.ask(question)
await ctx.report.say(message)
```

### 2.2 MVP 第一个 Demo

用户说：

```text
去厨房看看。
```

系统执行：

```text
1. resolve_place("厨房")
2. get_robot_state()
3. navigate_to("厨房")
4. inspect_area("厨房")
5. memory.remember("last_inspection", result)
6. report.say("厨房检查完成，未发现异常。")
```

### 2.3 MVP 暂不做

第一版禁止扩展到以下范围：

```text
复杂自然语言任务规划
完整长期 World Model
完整长期 Memory Manager
多 Agent 编排
App Store
复杂安全沙箱
真实机械臂抓取闭环
VLM 深度推理
多机器人调度
```

可以保留接口，但不要把它们作为第一版验收项。

---

## 3. 建议创建的 AGENTS.md

Codex 会优先读取仓库中的 `AGENTS.md`。请在仓库根目录创建或更新该文件。

```md
# AGENTS.md

## Project

This repository implements an Agentic OS / Agentic Runtime running above ROS2.

It is not a normal ROS2 application, not an LLM wrapper, and not a fork of ROS2.

The goal is to expose high-level, permissioned, safe, auditable robot capabilities to Agent Apps.

## Non-negotiable architecture boundaries

- Do not modify ROS2 source code.
- Do not place Agentic Runtime inside ROS2 as a normal business node.
- ROS2 bridge nodes are allowed.
- Agent Apps must not import rclpy.
- Agent Apps must not publish /cmd_vel.
- Agent Apps must not subscribe to /scan, /odom, or /tf directly.
- Agent Apps must not call Nav2 or MoveIt actions directly.
- LLM / Agent logic must never perform real-time closed-loop control.
- All robot movement must go through Agentic Runtime permission checks and safety_guard.

## Layering

Expected layers:

User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Robot Capability Layer
  -> ROS2 Bridge
  -> ROS2
  -> Robot Hardware

## MVP APIs

Agent Apps may only call high-level APIs:

- ctx.robot.get_state()
- ctx.robot.navigate_to(place)
- ctx.robot.inspect_area(place)
- ctx.robot.stop()
- ctx.world.resolve_place(name)
- ctx.memory.remember(key, value)
- ctx.memory.recall(key)
- ctx.human.ask(question)
- ctx.report.say(message)

## Done means

For every implementation task:

1. Code compiles.
2. Unit tests pass.
3. Integration or mock demo command is documented.
4. No forbidden ROS2 calls appear in Agent App code.
5. All dangerous robot actions go through safety_guard.
6. Errors return structured error codes.
7. The task writes or updates tests.
8. The final response lists changed files, commands run, and remaining risks.

## Preferred implementation style

- Python for MVP Runtime and ROS2 bridge.
- rclpy only inside ROS2 bridge packages.
- No rclpy inside agentic_runtime SDK or Agent Apps.
- YAML / JSON Schema for manifests.
- SQLite for MVP memory.
- JSONL for MVP audit logs.
- Mock backends are acceptable where real robot integrations are unavailable.

## Build and test

Common commands:

```bash
# ROS2 packages
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install

# Runtime
cd agentic_runtime
python -m pip install -e ".[dev]"
pytest -q

# Full static guard
python scripts/check_forbidden_imports.py
```
```

---

## 4. 推荐仓库结构

Codex 应把仓库整理为以下结构。已有仓库不同也可以适配，但最终必须体现这些边界。

```text
repo/
├── AGENTS.md
├── CODEX_IMPLEMENTATION_TASKBOOK.md
├── README.md
│
├── docs/
│   ├── architecture.md
│   ├── api_v0.1.md
│   ├── app_manifest_v0.1.md
│   ├── skill_manifest_v0.1.md
│   ├── safety_policy_v0.1.md
│   └── demo_room_inspection.md
│
├── configs/
│   ├── places.yaml
│   ├── permissions.yaml
│   ├── safety.yaml
│   └── runtime.yaml
│
├── ros2_ws/
│   └── src/
│       ├── agentic_msgs/
│       ├── agentic_capability_bridge/
│       ├── agentic_safety_guard/
│       ├── agentic_world_model/
│       └── agentic_app_runtime_bridge/
│
├── agentic_runtime/
│   ├── pyproject.toml
│   ├── agentic_runtime/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── config.py
│   │   ├── app_manager/
│   │   ├── permission_manager/
│   │   ├── skill_registry/
│   │   ├── skill_executor/
│   │   ├── memory/
│   │   ├── world_model_client/
│   │   ├── safety_client/
│   │   ├── ros_bridge_client/
│   │   ├── execution_monitor/
│   │   └── sdk/
│   │
│   ├── skills/
│   │   ├── get_robot_state.yaml
│   │   ├── resolve_place.yaml
│   │   ├── navigate_to.yaml
│   │   ├── inspect_area.yaml
│   │   ├── stop_robot.yaml
│   │   ├── memory_remember.yaml
│   │   ├── memory_recall.yaml
│   │   ├── human_ask.yaml
│   │   └── report_say.yaml
│   │
│   └── tests/
│
├── agentic_apps/
│   └── room_inspection_app/
│       ├── app.yaml
│       ├── main.py
│       ├── prompts/
│       │   └── system.md
│       ├── workflows/
│       │   └── default.yaml
│       ├── memory_schema.yaml
│       ├── tests/
│       └── README.md
│
└── scripts/
    ├── setup_env.sh
    ├── run_runtime.sh
    ├── run_ros_bridge.sh
    ├── run_demo_app.sh
    ├── check_forbidden_imports.py
    └── run_tests.sh
```

---

## 5. 全局技术选型

### 5.1 ROS2 版本

Codex 不要盲目升级 ROS2。根据系统 Ubuntu 版本选择：

```text
Ubuntu 22.04 -> ROS2 Humble
Ubuntu 24.04 -> ROS2 Jazzy
```

如果当前机器已经安装 `/opt/ros/humble`，MVP 以 Humble 为准。

### 5.2 语言

MVP 建议：

```text
ROS2 bridge: Python / rclpy
Agentic Runtime: Python
Agentic SDK: Python
Agent App: Python
```

后续可将性能敏感的 ROS2 bridge 或 safety_guard 改为 C++。

### 5.3 Runtime 与 ROS2 Bridge 通信

MVP 可先用两种模式之一：

```text
模式 A:
Agentic Runtime 直接通过本机 HTTP 调用 runtime_bridge_node 的接口。

模式 B:
Agentic Runtime 内部使用 ros_bridge_client，桥接到 ROS2 service/action。
```

为了避免 Runtime import `rclpy`，推荐：

```text
agentic_runtime 不 import rclpy。
只有 ros2_ws/src/* 里面的 ROS2 bridge packages import rclpy。
```

### 5.4 Memory

MVP：

```text
SQLite
```

后续：

```text
PostgreSQL
Vector database
```

### 5.5 Manifest

MVP：

```text
YAML manifest + Python validation
```

后续可补：

```text
JSON Schema
Pydantic model validation
```

---

## 6. 全局错误码规范

所有 skill 失败必须返回结构化错误码。

```text
PLACE_NOT_FOUND
FORBIDDEN_ZONE
ROBOT_NOT_LOCALIZED
ESTOP_PRESSED
PERMISSION_DENIED
RESOURCE_LOCKED
SCHEMA_INVALID
SKILL_TIMEOUT
SKILL_CANCELLED
NAVIGATION_TIMEOUT
NAVIGATION_REJECTED
NAVIGATION_FAILED
INSPECTION_FAILED
SAFETY_REJECTED
HUMAN_TIMEOUT
BACKEND_UNAVAILABLE
UNEXPECTED_ERROR
```

推荐返回结构：

```json
{
  "success": false,
  "error_code": "NAVIGATION_TIMEOUT",
  "reason": "navigate_to timed out after 120s",
  "recoverable": true,
  "suggested_recovery": ["retry", "ask_human", "cancel"],
  "audit_id": "audit_000001"
}
```

---

## 7. Phase 0 — 架构与仓库骨架

### T0.1 创建仓库骨架

#### 目标

创建基础目录，不实现业务逻辑。

#### Codex 步骤

1. 检查当前仓库目录。
2. 创建 `docs/`、`configs/`、`agentic_runtime/`、`agentic_apps/`、`ros2_ws/src/`、`scripts/`。
3. 创建空的 `README.md`、`AGENTS.md`。
4. 把本文保存为 `CODEX_IMPLEMENTATION_TASKBOOK.md`。
5. 不要创建过度复杂的代码。

#### 输出文件

```text
README.md
AGENTS.md
docs/architecture.md
docs/api_v0.1.md
docs/app_manifest_v0.1.md
docs/skill_manifest_v0.1.md
docs/safety_policy_v0.1.md
configs/places.yaml
configs/permissions.yaml
configs/safety.yaml
configs/runtime.yaml
scripts/run_tests.sh
```

#### 验收命令

```bash
test -f AGENTS.md
test -f docs/architecture.md
test -f configs/places.yaml
test -d ros2_ws/src
test -d agentic_runtime
test -d agentic_apps
```

#### 完成标准

- 仓库结构存在。
- 文档中明确写了：不修改 ROS2、不让 Agent App 直接接触 ROS2、不允许 LLM 控制实时闭环。

---

### T0.2 编写架构文档

#### 目标

生成工程团队能读懂的架构边界。

#### 输出文件

```text
docs/architecture.md
```

#### 必须包含

```text
1. 项目目标
2. 非目标
3. 分层架构图
4. 每层职责
5. Runtime 进程模型
6. ROS2 bridge 作用
7. Agent App 禁止项
8. MVP 范围
```

#### 必须包含架构图

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Robot Capability Layer
  -> ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

#### 验收命令

```bash
grep -n "不修改 ROS2" docs/architecture.md
grep -n "Agent App" docs/architecture.md
grep -n "ROS2 Bridge" docs/architecture.md
grep -n "/cmd_vel" docs/architecture.md
```

---

### T0.3 定义 App Manifest 文档

#### 目标

定义 Agent App 的 `app.yaml` 标准。

#### 输出文件

```text
docs/app_manifest_v0.1.md
```

#### 必须定义字段

```yaml
name: string
version: string
description: string
entrypoint: string
permissions: string[]
required_capabilities: string[]
safety_policy:
  allow_autonomous_navigation: bool
  allow_manipulation: bool
  require_human_confirmation_for: string[]
  forbidden_zones: string[]
  max_task_duration_s: int
runtime_limits:
  max_concurrent_tasks: int
  max_retries_per_skill: int
  max_memory_write_per_task: int
  llm_planning_enabled: bool
```

#### 验收命令

```bash
grep -n "permissions" docs/app_manifest_v0.1.md
grep -n "required_capabilities" docs/app_manifest_v0.1.md
grep -n "safety_policy" docs/app_manifest_v0.1.md
```

---

### T0.4 定义 Skill Manifest 文档

#### 目标

定义 skill/capability 的 manifest 标准。

#### 输出文件

```text
docs/skill_manifest_v0.1.md
```

#### 必须定义字段

```yaml
name: string
version: string
description: string

input_schema:
  type: object
  required: []
  properties: {}

output_schema:
  type: object
  required: []
  properties: {}

permission_requirements: string[]

resource_requirements:
  locks: string[]

safety_constraints:
  require_known_place: bool
  require_localized: bool
  require_estop_released: bool
  forbidden_zone_check: bool
  allow_cancel: bool
  max_duration_s: int

timeout_s: int

retry_policy:
  max_attempts: int
  retry_on: string[]

backend:
  type: ros2_action | ros2_service | ros2_topic | runtime_internal | mock
  bridge: string
  ros2_action_name: string
  ros2_action_type: string

observability:
  audit: bool
  record_feedback: bool
  record_result: bool
```

#### 验收命令

```bash
grep -n "permission_requirements" docs/skill_manifest_v0.1.md
grep -n "resource_requirements" docs/skill_manifest_v0.1.md
grep -n "safety_constraints" docs/skill_manifest_v0.1.md
grep -n "backend" docs/skill_manifest_v0.1.md
```

---

### T0.5 创建配置文件

#### 目标

创建 MVP 配置，供 Runtime 和 ROS2 bridge 使用。

#### 输出文件

```text
configs/places.yaml
configs/permissions.yaml
configs/safety.yaml
configs/runtime.yaml
```

#### `configs/places.yaml`

```yaml
places:
  厨房:
    id: kitchen
    frame_id: map
    pose:
      x: 3.2
      y: 1.5
      yaw: 1.57
    allowed: true

  客厅:
    id: living_room
    frame_id: map
    pose:
      x: 0.8
      y: 2.1
      yaw: 0.0
    allowed: true

  楼梯:
    id: stairs
    frame_id: map
    pose:
      x: 5.0
      y: 0.0
      yaw: 0.0
    allowed: false
```

#### `configs/permissions.yaml`

```yaml
permissions:
  robot.state.read:
    description: Read robot state.
  robot.move:
    description: Navigate robot base through approved capability.
  robot.stop:
    description: Stop or cancel active robot task.
  world.read:
    description: Read known places and world model.
  perception.inspect:
    description: Inspect a known area.
  memory.read:
    description: Read app memory.
  memory.write:
    description: Write app memory.
  human.ask:
    description: Ask human for confirmation or input.
  report.say:
    description: Report message to user.
```

#### `configs/safety.yaml`

```yaml
safety:
  require_estop_released: true
  max_linear_speed_mps: 0.5
  max_angular_speed_radps: 0.8
  max_navigation_duration_s: 120
  max_task_duration_s: 300
  forbidden_zones:
    - stairs
    - elevator
    - lab_restricted_zone
```

#### `configs/runtime.yaml`

```yaml
runtime:
  audit_log_path: ./var/audit/audit.jsonl
  memory_db_path: ./var/memory/memory.sqlite3
  default_skill_timeout_s: 60
  allow_mock_backends: true
  app_root: ./agentic_apps
  skill_root: ./agentic_runtime/skills
```

#### 验收命令

```bash
python - <<'PY'
import yaml
for p in [
  "configs/places.yaml",
  "configs/permissions.yaml",
  "configs/safety.yaml",
  "configs/runtime.yaml",
]:
    with open(p, "r", encoding="utf-8") as f:
        yaml.safe_load(f)
print("yaml ok")
PY
```

---

## 8. Phase 1 — ROS2 Capability Layer

> 本阶段只实现 ROS2 侧 package。Runtime 不要 import rclpy。

### T1.1 创建 `agentic_msgs`

#### 目标

创建 ROS2 interface package，定义 MVP 所需 msg/srv/action。

#### 路径

```text
ros2_ws/src/agentic_msgs/
```

#### 文件结构

```text
agentic_msgs/
├── CMakeLists.txt
├── package.xml
├── msg/
│   ├── Task.msg
│   ├── SkillDescription.msg
│   ├── WorldObject.msg
│   ├── RobotState.msg
│   ├── Place.msg
│   └── SafetyState.msg
├── srv/
│   ├── ResolvePlace.srv
│   ├── GetRobotState.srv
│   ├── StopRobot.srv
│   ├── InspectArea.srv
│   ├── AskHuman.srv
│   └── CheckSafety.srv
└── action/
    ├── ExecuteSkill.action
    └── NavigateToPlace.action
```

#### `msg/Place.msg`

```text
string id
string name
string frame_id
geometry_msgs/Pose pose
bool allowed
string metadata_json
```

#### `msg/RobotState.msg`

```text
string robot_id
string mode
string battery_state
float32 battery_percent
bool is_localized
bool is_moving
bool estop_pressed
string current_place
geometry_msgs/Pose pose
string active_task_id
string state_json
```

#### `msg/SafetyState.msg`

```text
bool estop_pressed
bool safety_ok
string[] active_forbidden_zones
string reason
string state_json
```

#### `srv/ResolvePlace.srv`

```text
string name
---
bool success
string error_code
string reason
agentic_msgs/Place place
```

#### `srv/GetRobotState.srv`

```text
---
bool success
string error_code
string reason
agentic_msgs/RobotState state
```

#### `srv/StopRobot.srv`

```text
string reason
string request_id
---
bool success
string error_code
string message
```

#### `srv/InspectArea.srv`

```text
string place
string request_id
int32 timeout_s
---
bool success
string error_code
string summary
string[] objects
string[] anomalies
string result_json
```

#### `srv/AskHuman.srv`

```text
string question
string[] options
int32 timeout_s
bool require_explicit_confirmation
---
bool answered
string answer
string reason
```

#### `srv/CheckSafety.srv`

```text
string skill_name
string args_json
string app_id
---
bool allowed
string error_code
string reason
```

#### `action/NavigateToPlace.action`

```text
string place
string request_id
int32 timeout_s
---
bool success
string error_code
string reason
string result_json
---
string status
float32 progress
string feedback_json
```

#### 验收命令

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-select agentic_msgs
source install/setup.bash
ros2 interface show agentic_msgs/srv/ResolvePlace
ros2 interface show agentic_msgs/action/NavigateToPlace
```

#### 完成标准

- `colcon build` 通过。
- `ros2 interface show` 能看到接口。
- 没有业务逻辑混入消息包。

---

### T1.2 创建 `agentic_world_model`

#### 目标

实现 `world_model_node`，提供地点解析服务。

#### 路径

```text
ros2_ws/src/agentic_world_model/
```

#### 服务

```text
/agentic/world/resolve_place
类型：agentic_msgs/srv/ResolvePlace
```

#### 行为

```text
输入: "厨房"
输出: success=true, place.id="kitchen", pose=...
```

```text
输入: "不存在的地方"
输出: success=false, error_code="PLACE_NOT_FOUND"
```

```text
输入: "楼梯"
输出: success=false, error_code="FORBIDDEN_ZONE" 或 success=true allowed=false
```

建议 MVP 返回：

```text
楼梯属于已知地点，但 allowed=false。
Runtime/safety_guard 决定是否拒绝。
```

#### 实现步骤

1. 创建 Python ROS2 package。
2. 从 `configs/places.yaml` 读取地点。
3. 提供 `ResolvePlace` service。
4. 增加 launch 文件。
5. 增加最小单测或脚本测试。

#### 验收命令

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-select agentic_world_model
source install/setup.bash
ros2 run agentic_world_model world_model_node
```

另开终端：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
ros2 service call /agentic/world/resolve_place agentic_msgs/srv/ResolvePlace "{name: '厨房'}"
```

#### 完成标准

- 能解析厨房。
- 未知地点返回 `PLACE_NOT_FOUND`。
- 服务不依赖 Runtime。

---

### T1.3 创建 `agentic_safety_guard`

#### 目标

实现安全检查与紧急停止服务。

#### 路径

```text
ros2_ws/src/agentic_safety_guard/
```

#### 服务

```text
/agentic/safety/check
类型：agentic_msgs/srv/CheckSafety

/agentic/robot/stop
类型：agentic_msgs/srv/StopRobot
```

#### MVP 行为

`CheckSafety`：

```text
navigate_to 厨房 -> allowed=true
navigate_to 楼梯 -> allowed=false, error_code=FORBIDDEN_ZONE
estop_pressed=true -> allowed=false, error_code=ESTOP_PRESSED
```

`StopRobot`：

```text
1. 取消当前导航任务，如果有。
2. 发布一次零速度到底盘 stop 通道，或在 mock 模式记录 stop。
3. 返回 success=true。
```

注意：

```text
stop_robot 是唯一允许触发底盘停止相关底层动作的安全入口。
Agent App 不允许直接 publish /cmd_vel。
```

#### 验收命令

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-select agentic_safety_guard
source install/setup.bash
ros2 run agentic_safety_guard safety_guard_node
```

另开终端：

```bash
ros2 service call /agentic/safety/check agentic_msgs/srv/CheckSafety "{skill_name: 'navigate_to', args_json: '{\"place\":\"楼梯\"}', app_id: 'room_inspection_app'}"
ros2 service call /agentic/robot/stop agentic_msgs/srv/StopRobot "{reason: 'manual_test', request_id: 'test_stop_001'}"
```

#### 完成标准

- forbidden zone 被拒绝。
- stop service 可用。
- 所有返回包含 error_code 和 reason。

---

### T1.4 创建 `agentic_capability_bridge`

#### 目标

创建 ROS2 bridge package，实现 navigation、state、inspection 三类 bridge。

#### 路径

```text
ros2_ws/src/agentic_capability_bridge/
```

#### 节点

```text
navigation_bridge_node
state_bridge_node
inspection_bridge_node
```

#### `state_bridge_node`

提供：

```text
/agentic/robot/get_state
类型：agentic_msgs/srv/GetRobotState
```

MVP 可以 mock：

```text
is_localized=true
is_moving=false
estop_pressed=false
battery_percent=80.0
current_place=""
```

#### `inspection_bridge_node`

提供：

```text
/agentic/perception/inspect_area
类型：agentic_msgs/srv/InspectArea
```

MVP mock 输出：

```text
place=厨房
summary=厨房检查完成，未发现异常。
objects=["table", "chair"]
anomalies=[]
```

#### `navigation_bridge_node`

提供：

```text
/agentic/robot/navigate_to_place
类型：agentic_msgs/action/NavigateToPlace
```

MVP 两种模式：

```text
mock_nav=true:
  不调用 Nav2，sleep 2 秒后返回 success。

mock_nav=false:
  调用 Nav2 NavigateToPose action。
```

第一版可以先做 mock，再接 Nav2。

#### 验收命令

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-select agentic_capability_bridge
source install/setup.bash

ros2 run agentic_capability_bridge state_bridge_node
ros2 run agentic_capability_bridge inspection_bridge_node
ros2 run agentic_capability_bridge navigation_bridge_node --ros-args -p mock_nav:=true
```

另开终端测试：

```bash
ros2 service call /agentic/robot/get_state agentic_msgs/srv/GetRobotState "{}"
ros2 service call /agentic/perception/inspect_area agentic_msgs/srv/InspectArea "{place: '厨房', request_id: 'inspect_001', timeout_s: 60}"
ros2 action send_goal /agentic/robot/navigate_to_place agentic_msgs/action/NavigateToPlace "{place: '厨房', request_id: 'nav_001', timeout_s: 120}" --feedback
```

#### 完成标准

- state service 可用。
- inspection service 可用。
- navigate action 可用。
- mock navigation 支持 cancel。
- bridge 内可以 import rclpy，但 Runtime 和 App 不可以。

---

### T1.5 创建 `agentic_app_runtime_bridge`

#### 目标

提供 Runtime 与 ROS2 bridge 的统一入口。MVP 可选，如果 Runtime 直接调各服务，则本任务可以延后。

#### 推荐职责

```text
1. 聚合 ROS2 capability service/action。
2. 向 Runtime 提供单一 ExecuteSkill action 或 HTTP bridge。
3. 发布 runtime event topic。
```

#### MVP 简化

第一版可以只实现：

```text
runtime_bridge_node
  - 接收 ExecuteSkill.action
  - 根据 skill_name 分发到 navigate/get_state/inspect/stop
```

#### 完成标准

- 如果实现本节点，Runtime 只需对接一个 ROS2 action。
- 如果不实现本节点，必须在 docs 中说明 Runtime 对接各 bridge service/action 的方式。

---

## 9. Phase 2 — Agentic Runtime MVP

> 本阶段实现 Python Runtime。严禁 Runtime import rclpy。

### T2.1 创建 Python package

#### 路径

```text
agentic_runtime/
```

#### 文件结构

```text
agentic_runtime/
├── pyproject.toml
├── agentic_runtime/
│   ├── __init__.py
│   ├── server.py
│   ├── config.py
│   ├── types.py
│   ├── errors.py
│   └── audit.py
└── tests/
    ├── test_config.py
    └── test_errors.py
```

#### `pyproject.toml` 依赖建议

```toml
[project]
name = "agentic-runtime"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "pydantic>=2",
  "pyyaml>=6",
  "fastapi>=0.110",
  "uvicorn>=0.27",
  "httpx>=0.26",
  "jsonschema>=4",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.23",
  "ruff>=0.5",
]
```

#### 验收命令

```bash
cd agentic_runtime
python -m pip install -e ".[dev]"
pytest -q
```

---

### T2.2 实现核心类型与错误模型

#### 目标

定义 Runtime 内部统一数据结构。

#### 文件

```text
agentic_runtime/agentic_runtime/types.py
agentic_runtime/agentic_runtime/errors.py
```

#### 必须定义

```python
class SkillResult
class SkillCall
class AppManifest
class SkillManifest
class RobotState
class PlaceRef
class InspectionResult
class HumanAnswer
```

#### 错误类

```python
class AgenticRuntimeError(Exception)
class PermissionDeniedError(AgenticRuntimeError)
class SafetyRejectedError(AgenticRuntimeError)
class SkillTimeoutError(AgenticRuntimeError)
class SkillExecutionError(AgenticRuntimeError)
class ResourceLockedError(AgenticRuntimeError)
class SchemaInvalidError(AgenticRuntimeError)
```

#### 完成标准

- 所有错误有 `code`、`message`、`recoverable`。
- 单测覆盖错误序列化。

---

### T2.3 实现 Skill Registry

#### 目标

加载 `agentic_runtime/skills/*.yaml`，校验并注册 skill。

#### 文件

```text
agentic_runtime/agentic_runtime/skill_registry/
├── __init__.py
├── registry.py
├── skill_manifest.py
└── schema_validator.py
```

#### 行为

```text
1. 启动时读取 skill_root。
2. 每个 YAML 转成 SkillManifest。
3. 检查 name/version/input_schema/output_schema/permissions/backend。
4. 支持 get_skill(name)。
5. 如果 manifest 无效，启动失败。
```

#### 必须实现的 skill manifest

```text
get_robot_state.yaml
resolve_place.yaml
navigate_to.yaml
inspect_area.yaml
stop_robot.yaml
memory_remember.yaml
memory_recall.yaml
human_ask.yaml
report_say.yaml
```

#### 验收命令

```bash
cd agentic_runtime
pytest -q tests/test_skill_registry.py
```

#### 单测要求

```text
1. 能加载全部 9 个 MVP skill。
2. 缺失 name 会失败。
3. 缺失 permission_requirements 会失败。
4. get_skill("navigate_to") 返回正确 backend。
```

---

### T2.4 实现 Permission Manager

#### 目标

根据 App manifest 和 Skill manifest 执行权限检查。

#### 文件

```text
agentic_runtime/agentic_runtime/permission_manager/
├── __init__.py
├── permissions.py
└── policy_engine.py
```

#### 行为

```text
allowed = app.permissions 包含 skill.permission_requirements 的全部权限
否则拒绝
```

#### 示例

```text
room_inspection_app 有 robot.move
navigate_to 需要 robot.move
=> allowed

room_inspection_app 没有 manipulation.pick
pick_object 需要 manipulation.pick
=> PERMISSION_DENIED
```

#### 验收命令

```bash
cd agentic_runtime
pytest -q tests/test_permission_manager.py
```

---

### T2.5 实现 Resource Manager

#### 目标

防止多个 App 同时占用底盘、相机、机械臂等资源。

#### 文件

```text
agentic_runtime/agentic_runtime/skill_executor/resource_manager.py
```

#### 资源锁

```text
base
camera
arm
gripper
speaker
```

#### 行为

```text
1. acquire(resource, session_id, skill_call_id)
2. release(resource, session_id, skill_call_id)
3. release_by_session(session_id)
4. 如果资源已被其他 session 占用，返回 RESOURCE_LOCKED。
```

#### 完成标准

- 单测覆盖重复锁。
- 单测覆盖 App 崩溃后 release_by_session。
- stop_robot 不应被普通 resource lock 阻塞。

---

### T2.6 实现 Memory MVP

#### 目标

实现 `memory.remember()` 与 `memory.recall()`。

#### 文件

```text
agentic_runtime/agentic_runtime/memory/
├── __init__.py
├── memory_store.py
└── sqlite_store.py
```

#### SQLite 表

```sql
CREATE TABLE IF NOT EXISTS memory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  app_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(app_id, key)
);
```

#### 行为

```text
remember(app_id, session_id, key, value)
recall(app_id, key)
```

#### 验收命令

```bash
cd agentic_runtime
pytest -q tests/test_memory.py
```

---

### T2.7 实现 ROS Bridge Client

#### 目标

Runtime 不 import rclpy，通过 shell/HTTP/mock/client 调用 ROS2 bridge。

#### 文件

```text
agentic_runtime/agentic_runtime/ros_bridge_client/
├── __init__.py
├── client.py
├── mock_client.py
└── types.py
```

#### MVP 推荐

先实现 `MockRosBridgeClient`，支持：

```python
await client.resolve_place("厨房")
await client.get_robot_state()
await client.navigate_to("厨房", timeout_s=120)
await client.inspect_area("厨房", timeout_s=60)
await client.stop_robot("reason")
```

之后再替换为真实 ROS bridge client。

#### 完成标准

- Runtime 单测不需要 ROS2 环境。
- Mock client 能跑 room_inspection_app。
- 接口与未来真实 ROS bridge client 一致。

---

### T2.8 实现 Skill Executor

#### 目标

实现统一执行状态机。

#### 文件

```text
agentic_runtime/agentic_runtime/skill_executor/
├── __init__.py
├── executor.py
├── dispatcher.py
├── timeout.py
├── cancellation.py
└── resource_manager.py
```

#### 状态机

```text
created
  -> schema_validated
  -> permission_checked
  -> safety_checked
  -> resource_locked
  -> dispatched
  -> running
  -> succeeded

失败:
  -> rejected
  -> timeout
  -> cancelled
  -> failed
```

#### 执行前

```text
1. 输入 schema 校验
2. App 权限检查
3. Safety check
4. Resource lock
```

#### 执行中

```text
1. timeout monitor
2. cancellation handle
3. backend call
```

#### 执行后

```text
1. audit log
2. release resource
3. return SkillResult
```

#### 验收命令

```bash
cd agentic_runtime
pytest -q tests/test_skill_executor.py
```

#### 单测必须覆盖

```text
1. navigate_to 成功。
2. navigate_to 缺权限被拒绝。
3. navigate_to 资源被占用被拒绝。
4. navigate_to timeout 后释放 base lock。
5. stop_robot 不被普通锁阻塞。
6. inspect_area 成功。
7. memory_remember / memory_recall 成功。
```

---

### T2.9 实现 Agentic SDK

#### 目标

给 Agent App 提供稳定高级 API。

#### 文件

```text
agentic_runtime/agentic_runtime/sdk/
├── __init__.py
├── context.py
├── robot.py
├── world.py
├── perception.py
├── manipulation.py
├── memory.py
├── human.py
└── report.py
```

#### API

```python
class AgentContext:
    robot: RobotAPI
    world: WorldAPI
    memory: MemoryAPI
    human: HumanAPI
    report: ReportAPI
```

#### `RobotAPI`

```python
async def get_state(self): ...
async def navigate_to(self, place: str, timeout_s: int = 120): ...
async def inspect_area(self, place: str, timeout_s: int = 60): ...
async def stop(self, reason: str = "app_requested"): ...
```

#### `WorldAPI`

```python
async def resolve_place(self, name: str): ...
async def get_places(self): ...
async def locate_user(self): ...
```

#### `MemoryAPI`

```python
async def remember(self, key: str, value): ...
async def recall(self, key: str, default=None): ...
```

#### `HumanAPI`

```python
async def ask(self, question: str, options=None, timeout_s: int = 60, require_confirmation: bool = False): ...
```

#### `ReportAPI`

```python
async def say(self, message: str): ...
async def log(self, message: str, level: str = "info"): ...
```

#### 禁止

SDK 不允许：

```text
import rclpy
出现 /cmd_vel
出现 /scan
出现 /odom
出现 /tf
```

#### 验收命令

```bash
cd agentic_runtime
pytest -q tests/test_sdk.py
grep -R "import rclpy\|/cmd_vel\|/scan\|/odom\|/tf" agentic_runtime/sdk && exit 1 || true
```

---

### T2.10 实现 Runtime Server 和 CLI

#### 目标

让 Runtime 可启动、可执行 App、可查看状态。

#### 文件

```text
agentic_runtime/agentic_runtime/server.py
agentic_runtime/agentic_runtime/app_manager/
agentic_runtime/agentic_runtime/execution_monitor/
agentic_runtime/agentic_runtime/cli.py
```

#### MVP CLI

```bash
agenticctl status
agentic-run room_inspection_app --place 厨房
```

如果暂时不做安装命令，也可以提供：

```bash
python -m agentic_runtime.cli status
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房
```

#### `agenticctl status` 至少输出

```text
agenticd: running
ros_bridge: mock 或 connected
skills:
  - get_robot_state: ready
  - resolve_place: ready
  - navigate_to: ready
  - inspect_area: ready
  - stop_robot: ready
sessions:
  - ...
resource_locks:
  - base: free
recent_syscalls:
  - ...
```

#### 完成标准

- 可以本地 mock 跑通 App。
- 可以看到 audit log。
- 可以看到 skill registry 状态。

---

## 10. Phase 3 — Agent App MVP

### T3.1 创建 `room_inspection_app`

#### 目标

实现第一个 Agent App。

#### 路径

```text
agentic_apps/room_inspection_app/
```

#### 文件结构

```text
room_inspection_app/
├── app.yaml
├── main.py
├── prompts/
│   └── system.md
├── workflows/
│   └── default.yaml
├── memory_schema.yaml
├── tests/
│   ├── test_app_manifest.py
│   └── test_room_inspection_flow.py
└── README.md
```

#### `app.yaml`

```yaml
name: room_inspection_app
version: 0.1.0
description: Inspect a named room using robot navigation and perception.

entrypoint: main:run

permissions:
  - robot.state.read
  - robot.move
  - robot.stop
  - world.read
  - perception.inspect
  - memory.read
  - memory.write
  - human.ask
  - report.say

required_capabilities:
  - robot.get_state
  - robot.navigate_to
  - robot.inspect_area
  - robot.stop
  - world.resolve_place
  - memory.remember
  - memory.recall
  - human.ask
  - report.say

safety_policy:
  allow_autonomous_navigation: true
  allow_manipulation: false
  require_human_confirmation_for:
    - entering_restricted_area
    - moving_near_human
    - retry_after_navigation_failure
  forbidden_zones:
    - stairs
    - elevator
    - lab_restricted_zone
  max_task_duration_s: 300
  max_navigation_duration_s: 120
  stop_on_human_request: true

runtime_limits:
  max_concurrent_tasks: 1
  max_retries_per_skill: 1
  max_memory_write_per_task: 20
  llm_planning_enabled: false
```

#### `main.py`

```python
from agentic_runtime.sdk import AgentContext
from agentic_runtime.errors import SafetyRejectedError, SkillExecutionError, SkillTimeoutError


async def run(ctx: AgentContext, place: str = "厨房"):
    await ctx.report.say(f"收到任务：准备去{place}检查。")

    try:
        state = await ctx.robot.get_state()
        if state.estop_pressed:
            await ctx.report.say("机器人处于急停状态，无法执行任务。")
            return {"success": False, "reason": "ESTOP_PRESSED"}

        resolved = await ctx.world.resolve_place(place)
        if not resolved or not resolved.allowed:
            await ctx.report.say(f"地点不可用：{place}")
            return {"success": False, "reason": "PLACE_NOT_AVAILABLE"}

        await ctx.memory.remember("last_requested_place", place)

        nav_result = await ctx.robot.navigate_to(place, timeout_s=120)
        if not nav_result.success:
            answer = await ctx.human.ask(
                question=f"导航到{place}失败，是否重试一次？",
                options=["重试", "取消任务"],
                timeout_s=30,
                require_confirmation=True,
            )
            if answer.answer == "重试":
                nav_result = await ctx.robot.navigate_to(place, timeout_s=120)
            else:
                await ctx.robot.stop(reason="navigation_failed_user_cancelled")
                await ctx.report.say("任务已取消。")
                return {"success": False, "reason": "NAVIGATION_FAILED"}

        inspection = await ctx.robot.inspect_area(place, timeout_s=60)

        await ctx.memory.remember(
            "last_inspection",
            {
                "place": place,
                "summary": inspection.summary,
                "objects": inspection.objects,
                "anomalies": inspection.anomalies,
            },
        )

        if inspection.anomalies:
            message = f"{place}检查完成，发现异常：{inspection.anomalies}"
        else:
            message = f"{place}检查完成，未发现异常。"

        await ctx.report.say(message)

        return {
            "success": True,
            "place": place,
            "inspection": inspection.to_dict(),
        }

    except SafetyRejectedError as exc:
        await ctx.robot.stop(reason="safety_rejected")
        await ctx.report.say(f"任务被安全系统拒绝：{exc}")
        return {"success": False, "reason": "SAFETY_REJECTED"}

    except SkillTimeoutError as exc:
        await ctx.robot.stop(reason="task_timeout")
        await ctx.report.say("任务超时，机器人已停止。")
        return {"success": False, "reason": "TIMEOUT", "detail": str(exc)}

    except SkillExecutionError as exc:
        await ctx.robot.stop(reason="skill_execution_error")
        await ctx.report.say(f"任务执行失败：{exc}")
        return {"success": False, "reason": "SKILL_EXECUTION_ERROR"}

    except Exception as exc:
        await ctx.robot.stop(reason="unexpected_error")
        await ctx.report.say("任务出现未知错误，机器人已停止。")
        return {"success": False, "reason": "UNEXPECTED_ERROR", "detail": str(exc)}
```

#### `prompts/system.md`

```md
你是 room_inspection_app 的任务执行 Agent。

职责：
- 根据用户指定地点执行房间检查任务。
- 只能调用 Agentic OS 高级 API。
- 不允许直接访问 ROS2 topic、service、action。
- 不允许直接控制底盘、电机、机械臂。
- 遇到未知地点、禁入区域、导航失败、感知不确定、危险动作时，必须请求人工确认。
- 所有移动必须通过 ctx.robot.navigate_to(place)。
- 所有停止必须通过 ctx.robot.stop()。
- 所有记忆写入必须通过 ctx.memory.remember()。
- 所有对用户汇报必须通过 ctx.report.say()。

禁止行为：
- 不要 publish /cmd_vel。
- 不要 subscribe /scan。
- 不要读取 /odom 或 /tf。
- 不要直接调用 Nav2 action。
- 不要生成底层控制指令。
```

#### `workflows/default.yaml`

```yaml
name: default_room_inspection
version: 0.1.0

inputs:
  place:
    type: string
    default: 厨房

steps:
  - id: resolve_place
    call: world.resolve_place
    args:
      name: "{{ place }}"
    on_error: stop_and_report

  - id: check_state
    call: robot.get_state
    on_error: stop_and_report

  - id: navigate
    call: robot.navigate_to
    args:
      place: "{{ place }}"
      timeout_s: 120
    on_error: ask_human_retry_or_cancel

  - id: inspect
    call: robot.inspect_area
    args:
      place: "{{ place }}"
      timeout_s: 60
    on_error: report_inspection_failed

  - id: remember
    call: memory.remember
    args:
      key: last_inspection
      value:
        place: "{{ place }}"
        result: "{{ steps.inspect.output }}"

  - id: report
    call: report.say
    args:
      message: "{{ steps.inspect.output.summary }}"
```

#### 验收命令

```bash
python scripts/check_forbidden_imports.py
cd agentic_runtime
pytest -q
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --mock
```

#### 完成标准

- App 跑通 “去厨房看看”。
- App 不 import rclpy。
- App 不出现 ROS topic/action 名称。
- App 有错误处理。
- App 写入 memory。
- App 输出 report。

---

## 11. Phase 4 — 安全与执行监控

### T4.1 实现 forbidden import/static guard

#### 目标

CI 阻止 App 绕过 Agentic OS。

#### 文件

```text
scripts/check_forbidden_imports.py
```

#### 检查范围

```text
agentic_apps/
agentic_runtime/agentic_runtime/sdk/
```

#### 禁止词

```python
FORBIDDEN_PATTERNS = [
    "import rclpy",
    "from rclpy",
    "/cmd_vel",
    "/scan",
    "/odom",
    "/tf",
    "NavigateToPose",
    "MoveGroup",
    "ActionClient",
    "create_publisher",
    "create_subscription",
]
```

#### 验收命令

```bash
python scripts/check_forbidden_imports.py
```

#### 完成标准

- 如果在 App 里写 `import rclpy`，脚本失败。
- ROS2 bridge package 不在禁止范围内。

---

### T4.2 实现 Audit Logger

#### 目标

所有 skill call 都写 JSONL 审计日志。

#### 文件

```text
agentic_runtime/agentic_runtime/audit.py
```

#### JSONL 字段

```json
{
  "audit_id": "audit_000001",
  "timestamp": "2026-06-12T10:00:00Z",
  "app_id": "room_inspection_app",
  "session_id": "sess_001",
  "skill_name": "navigate_to",
  "args": {"place": "厨房"},
  "permission_result": "allowed",
  "safety_result": "allowed",
  "resource_lock_result": "locked",
  "backend": "mock",
  "status": "succeeded",
  "error_code": "",
  "duration_ms": 2300
}
```

#### 验收命令

```bash
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --mock
test -f var/audit/audit.jsonl
tail -n 5 var/audit/audit.jsonl
```

#### 完成标准

- 每个 skill 都有日志。
- 失败也有日志。
- 日志可按 session_id 查询。

---

### T4.3 实现 timeout 与 cancel

#### 目标

确保导航等长任务可以超时取消。

#### 行为

```text
navigate_to timeout_s 到达:
  1. cancel backend call
  2. release base lock
  3. write audit log
  4. return SKILL_TIMEOUT or NAVIGATION_TIMEOUT
```

#### 单测

```text
1. mock navigate sleep 5s，timeout_s=1。
2. 返回 timeout。
3. base lock 被释放。
4. audit log 有 timeout。
```

---

## 12. Phase 5 — 仿真与真实机器人测试

### T5.1 Mock 全链路测试

#### 目标

不依赖真实 ROS2/机器人，先跑通完整 Runtime + App。

#### 命令

```bash
python scripts/check_forbidden_imports.py
cd agentic_runtime
pytest -q
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --mock
python -m agentic_runtime.cli status
```

#### 验收

```text
1. App 成功返回 success=true。
2. audit log 包含 resolve_place/get_state/navigate_to/inspect_area/memory/report。
3. memory 中有 last_inspection。
4. App 没有 forbidden imports。
```

---

### T5.2 ROS2 Bridge Mock 测试

#### 目标

使用 ROS2 bridge mock 跑通。

#### 命令

终端 1：

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
ros2 run agentic_world_model world_model_node
```

终端 2：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
ros2 run agentic_safety_guard safety_guard_node
```

终端 3：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
ros2 run agentic_capability_bridge navigation_bridge_node --ros-args -p mock_nav:=true
```

终端 4：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
ros2 run agentic_capability_bridge state_bridge_node
```

终端 5：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
ros2 run agentic_capability_bridge inspection_bridge_node
```

终端 6：

```bash
cd agentic_runtime
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房
```

#### 验收

```text
1. ROS2 services/actions 有响应。
2. Runtime 不 import rclpy。
3. App 不 import rclpy。
4. Demo 成功。
```

---

### T5.3 Nav2 接入测试

#### 目标

把 `navigation_bridge_node` 从 mock 切到 Nav2。

#### 前置条件

```text
1. robot bringup 已启动。
2. Nav2 已启动。
3. map 已加载。
4. robot 已定位。
5. places.yaml 中厨房 pose 合法。
```

#### 命令

```bash
ros2 action list | grep navigate
ros2 action info /navigate_to_pose
ros2 run agentic_capability_bridge navigation_bridge_node --ros-args -p mock_nav:=false
```

#### 验收

```text
1. navigate_to("厨房") 能发送 Nav2 goal。
2. 能收到 feedback。
3. 成功时返回 success=true。
4. timeout 时 cancel goal。
5. forbidden zone 不发送 Nav2 goal。
```

---

## 13. Skill Manifest 文件内容

Codex 在 T2.3 创建以下文件。

### `agentic_runtime/skills/resolve_place.yaml`

```yaml
name: world.resolve_place
version: 0.1.0
description: Resolve a human-readable place name into a registered place.

input_schema:
  type: object
  required: [name]
  properties:
    name:
      type: string

output_schema:
  type: object
  required: [success]
  properties:
    success:
      type: boolean
    place:
      type: object
    error_code:
      type: string

permission_requirements:
  - world.read

resource_requirements:
  locks: []

safety_constraints:
  require_known_place: false
  require_estop_released: false
  allow_cancel: false

timeout_s: 3

retry_policy:
  max_attempts: 0
  retry_on: []

backend:
  type: mock
  bridge: world_model
  service: /agentic/world/resolve_place

observability:
  audit: true
  record_feedback: false
  record_result: true
```

### `agentic_runtime/skills/get_robot_state.yaml`

```yaml
name: robot.get_state
version: 0.1.0
description: Get current robot state.

input_schema:
  type: object
  required: []
  properties: {}

output_schema:
  type: object
  required: [success, state]
  properties:
    success:
      type: boolean
    state:
      type: object

permission_requirements:
  - robot.state.read

resource_requirements:
  locks: []

safety_constraints:
  require_estop_released: false
  allow_cancel: false

timeout_s: 3

retry_policy:
  max_attempts: 0
  retry_on: []

backend:
  type: mock
  bridge: state_bridge_node
  service: /agentic/robot/get_state

observability:
  audit: true
  record_feedback: false
  record_result: true
```

### `agentic_runtime/skills/navigate_to.yaml`

```yaml
name: robot.navigate_to
version: 0.1.0
description: Navigate robot to a registered place.

input_schema:
  type: object
  required: [place]
  properties:
    place:
      type: string
    timeout_s:
      type: integer
      minimum: 1
      maximum: 300

output_schema:
  type: object
  required: [success, reason]
  properties:
    success:
      type: boolean
    reason:
      type: string
    error_code:
      type: string
    result:
      type: object

permission_requirements:
  - robot.move

resource_requirements:
  locks:
    - base

safety_constraints:
  require_known_place: true
  require_localized: true
  require_estop_released: true
  forbidden_zone_check: true
  allow_cancel: true
  max_duration_s: 120
  max_linear_speed_mps: 0.5

timeout_s: 120

retry_policy:
  max_attempts: 1
  retry_on:
    - NAVIGATION_TRANSIENT_FAILURE

backend:
  type: mock
  bridge: navigation_bridge_node
  action: /agentic/robot/navigate_to_place
  ros2_backend_action: /navigate_to_pose
  ros2_backend_action_type: nav2_msgs/action/NavigateToPose

observability:
  audit: true
  record_feedback: true
  record_result: true
```

### `agentic_runtime/skills/inspect_area.yaml`

```yaml
name: robot.inspect_area
version: 0.1.0
description: Inspect a registered place and return a summary.

input_schema:
  type: object
  required: [place]
  properties:
    place:
      type: string
    timeout_s:
      type: integer
      minimum: 1
      maximum: 120

output_schema:
  type: object
  required: [success, summary]
  properties:
    success:
      type: boolean
    summary:
      type: string
    objects:
      type: array
    anomalies:
      type: array

permission_requirements:
  - perception.inspect

resource_requirements:
  locks:
    - camera

safety_constraints:
  require_known_place: true
  require_estop_released: false
  allow_cancel: true

timeout_s: 60

retry_policy:
  max_attempts: 0
  retry_on: []

backend:
  type: mock
  bridge: inspection_bridge_node
  service: /agentic/perception/inspect_area

observability:
  audit: true
  record_feedback: false
  record_result: true
```

### `agentic_runtime/skills/stop_robot.yaml`

```yaml
name: robot.stop
version: 0.1.0
description: Stop robot immediately through safety guard.

input_schema:
  type: object
  required: []
  properties:
    reason:
      type: string

output_schema:
  type: object
  required: [success]
  properties:
    success:
      type: boolean
    message:
      type: string

permission_requirements:
  - robot.stop

resource_requirements:
  locks: []

safety_constraints:
  highest_priority: true
  bypass_normal_queue: true
  audit_required: true
  allow_cancel: false

timeout_s: 2

retry_policy:
  max_attempts: 0
  retry_on: []

backend:
  type: mock
  bridge: safety_guard_node
  service: /agentic/robot/stop

observability:
  audit: true
  record_feedback: false
  record_result: true
```

---

## 14. CI 与测试

### 14.1 最小 CI 步骤

```bash
python scripts/check_forbidden_imports.py

cd agentic_runtime
python -m pip install -e ".[dev]"
ruff check .
pytest -q

cd ../ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

### 14.2 如果没有 ROS2 环境

允许跳过 ROS2 build，但必须跑：

```bash
python scripts/check_forbidden_imports.py
cd agentic_runtime
python -m pip install -e ".[dev]"
pytest -q
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --mock
```

### 14.3 必须有的测试文件

```text
agentic_runtime/tests/test_skill_registry.py
agentic_runtime/tests/test_permission_manager.py
agentic_runtime/tests/test_resource_manager.py
agentic_runtime/tests/test_memory.py
agentic_runtime/tests/test_skill_executor.py
agentic_runtime/tests/test_sdk.py
agentic_runtime/tests/test_room_inspection_flow.py
agentic_apps/room_inspection_app/tests/test_app_manifest.py
scripts/check_forbidden_imports.py
```

---

## 15. Codex 任务执行模板

每次给 Codex 派任务时，用以下格式。

```md
请执行任务：T<编号> <任务名>

背景：
- 本项目是运行在 ROS2 之上的 Agentic OS / Agentic Runtime。
- 不修改 ROS2 源码。
- Agent App 不允许直接接触 ROS2。
- Runtime 不允许 import rclpy。
- 只有 ros2_ws/src 下的 bridge package 可以 import rclpy。

任务目标：
<写清楚本次只做什么>

需要修改/创建的文件：
<列出文件>

具体步骤：
1. 先读取 AGENTS.md 和 CODEX_IMPLEMENTATION_TASKBOOK.md。
2. 检查现有文件，不要覆盖已有实现。
3. 按任务书实现。
4. 增加或更新测试。
5. 运行验收命令。
6. 输出变更文件、命令结果、未完成事项。

验收命令：
```bash
<commands>
```

完成标准：
- <标准 1>
- <标准 2>
- <标准 3>

禁止：
- 不要实现超出本任务范围的功能。
- 不要修改 /opt/ros。
- 不要让 Agent App import rclpy。
```

---

## 16. 推荐的第一批 Codex Prompt

### Prompt 1：创建仓库骨架

```md
请执行 T0.1 创建仓库骨架。

只创建基础目录、README、AGENTS.md、docs、configs、scripts，不要实现 Runtime 或 ROS2 节点。

完成后运行：
test -f AGENTS.md
test -f docs/architecture.md
test -f configs/places.yaml
test -d ros2_ws/src
test -d agentic_runtime
test -d agentic_apps
```

### Prompt 2：创建 manifest 文档和配置

```md
请执行 T0.2、T0.3、T0.4、T0.5。

输出：
- docs/architecture.md
- docs/app_manifest_v0.1.md
- docs/skill_manifest_v0.1.md
- docs/safety_policy_v0.1.md
- configs/places.yaml
- configs/permissions.yaml
- configs/safety.yaml
- configs/runtime.yaml

不要写任何 ROS2 节点或 Runtime 代码。
```

### Prompt 3：创建 agentic_msgs

```md
请执行 T1.1 创建 ros2_ws/src/agentic_msgs。

要求：
- 定义 Task.msg、SkillDescription.msg、WorldObject.msg、RobotState.msg、Place.msg、SafetyState.msg。
- 定义 ResolvePlace.srv、GetRobotState.srv、StopRobot.srv、InspectArea.srv、AskHuman.srv、CheckSafety.srv。
- 定义 ExecuteSkill.action、NavigateToPlace.action。
- 确保 colcon build 通过。

不要实现业务节点。
```

### Prompt 4：创建 ROS2 world model 和 bridge mock

```md
请执行 T1.2、T1.3、T1.4 的 mock 版本。

要求：
- world_model_node 可解析 configs/places.yaml。
- safety_guard_node 可拒绝 forbidden zone。
- state_bridge_node 返回 mock RobotState。
- inspection_bridge_node 返回 mock inspection result。
- navigation_bridge_node 支持 mock NavigateToPlace action。

不要接真实 Nav2。
```

### Prompt 5：创建 Runtime 核心

```md
请执行 T2.1、T2.2、T2.3、T2.4、T2.5。

要求：
- 创建 Python package。
- 实现核心类型、错误模型、Skill Registry、Permission Manager、Resource Manager。
- 创建 9 个 MVP skill manifests。
- Runtime 不允许 import rclpy。
- 增加 pytest 单测。
```

### Prompt 6：实现 Runtime Executor + SDK + Mock Demo

```md
请执行 T2.6、T2.7、T2.8、T2.9、T2.10。

要求：
- 实现 SQLite memory。
- 实现 MockRosBridgeClient。
- 实现 SkillExecutor 状态机。
- 实现 ctx.* SDK。
- 实现 CLI: python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --mock
- 增加测试。
```

### Prompt 7：实现 room_inspection_app

```md
请执行 T3.1。

要求：
- 创建 room_inspection_app。
- app.yaml 权限完整。
- main.py 只调用 ctx.* API。
- prompts/system.md 明确禁止直接 ROS2 调用。
- workflows/default.yaml 描述流程。
- 增加 App manifest 测试和 flow 测试。
```

### Prompt 8：实现安全扫描和审计

```md
请执行 T4.1、T4.2、T4.3。

要求：
- scripts/check_forbidden_imports.py 可阻止 App 使用 rclpy、/cmd_vel、/scan、/odom、/tf、NavigateToPose。
- 每个 skill call 写 audit JSONL。
- timeout 后释放资源锁。
- stop_robot 可中断或标记取消 active task。
```

---

## 17. 最终 Demo 验收标准

最终 MVP 必须通过以下验收。

### 17.1 静态验收

```bash
python scripts/check_forbidden_imports.py
```

必须通过。

### 17.2 Runtime 单测

```bash
cd agentic_runtime
pytest -q
```

必须通过。

### 17.3 Mock Demo

```bash
cd agentic_runtime
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --mock
```

期望输出包含：

```text
收到任务：准备去厨房检查。
厨房检查完成，未发现异常。
success=true
```

### 17.4 Forbidden Zone Demo

```bash
python -m agentic_runtime.cli run-app room_inspection_app --place 楼梯 --mock
```

期望输出包含：

```text
FORBIDDEN_ZONE
或 PLACE_NOT_AVAILABLE
success=false
```

### 17.5 Permission Denied Demo

构造一个缺少 `robot.move` 权限的测试 App，调用 `ctx.robot.navigate_to("厨房")`。

期望：

```text
PERMISSION_DENIED
没有发送 navigation backend call
audit log 记录拒绝原因
```

### 17.6 Timeout Demo

设置 mock navigation sleep 5 秒，调用 timeout_s=1。

期望：

```text
NAVIGATION_TIMEOUT 或 SKILL_TIMEOUT
base lock 被释放
audit log 记录 timeout
```

### 17.7 Stop Demo

导航过程中调用：

```python
await ctx.robot.stop(reason="manual_stop")
```

期望：

```text
active navigation cancelled
stop_robot audit log 生成
```

---

## 18. 禁止验收通过的情况

出现以下任一情况，MVP 不允许验收通过。

```text
1. Agent App import rclpy。
2. Agent App 直接 publish /cmd_vel。
3. Agent App 直接 call Nav2 action。
4. Runtime import rclpy。
5. navigate_to 没有 permission check。
6. navigate_to 没有 resource lock。
7. navigate_to timeout 后没有释放 base lock。
8. forbidden zone 仍然发送 navigation goal。
9. stop_robot 被普通任务队列阻塞。
10. 失败没有结构化 error_code。
11. 没有 audit log。
12. 需要修改 ROS2 源码才能跑。
```

---

## 19. 工程完成定义

MVP 完成时，仓库必须具备：

```text
1. docs 完整说明架构和边界。
2. ROS2 packages 可 build。
3. Runtime pytest 通过。
4. room_inspection_app 可 mock 跑通。
5. 禁止项扫描通过。
6. 至少 9 个 MVP skill 注册成功。
7. 每个 skill 有 manifest。
8. 每次 skill 调用有 audit log。
9. stop_robot 可用。
10. forbidden zone 可拒绝。
11. timeout 可取消并释放资源。
12. Agent App 不直接接触 ROS2。
```

---

## 20. 第一阶段最终执行建议

Codex 应按以下顺序执行，不能跳步。

```text
1. T0.1 仓库骨架
2. T0.2-T0.5 文档、manifest、config
3. T1.1 agentic_msgs
4. T1.2-T1.4 ROS2 bridge mock
5. T2.1-T2.5 Runtime core
6. T2.6-T2.10 Executor、SDK、CLI
7. T3.1 room_inspection_app
8. T4.1-T4.3 安全扫描、审计、timeout/cancel
9. T5.1 mock demo
10. T5.2 ROS2 bridge mock demo
11. T5.3 Nav2 接入
```

第一阶段不要实现真实机械臂，不要做复杂 LLM planner，不要做多 Agent。

真正要展示的是：

```text
一个不直接接触 ROS2 的 Agent App，
通过 Agentic SDK 调用高级能力，
经过 Runtime 权限、资源锁、安全检查、skill executor、ROS2 bridge，
最终完成“去厨房看看”的可审计、可取消、安全受控闭环。
```
