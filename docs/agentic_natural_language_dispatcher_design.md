# AgenticOS 自然语言入口与调度 Agent 设计

最后更新：2026-06-15

本文设计 AgenticOS 的下一阶段入口形态：用户不再优先记忆 `agentic photo`、`agentic-run inspection_agent` 这类子命令，而是直接向 AgenticOS 输入自然语言。AgenticOS 先由一个系统级调度 Agent 理解任务、生成受限 plan、选择具体 Agent App，然后再由被选中的 Agent App 完成任务。

本文是设计文档，不改变真实机器人安全边界：

- Agent App / Runtime / SDK 不得 import `rclpy`。
- Agent App 不得直接订阅相机 topic。
- Agent App 不得直接发布 servo topic。
- Agent App 不得直接调用 MoveIt、Nav2、kinematics、`/cmd_vel`、`/scan`、`/odom`、`/tf`。
- 只有 `/home/ubuntu/agentic_ws/ros2_bridge_src/*` 下的 ROS2 bridge package 可以 import `rclpy`。
- LLM / VLM 不能执行实时闭环控制。
- 所有真实机器人运动仍必须经过 Runtime permission、resource lock、safety guard、bridge allowlist、timeout、audit。
- `/opt/agentic` 仍是 installed AgenticOS root。
- `/home/ubuntu/agentic_ws/src` 仍是当前 Agent App/source workspace。
- `/home/ubuntu/agentic_ws/ros2_bridge_src` 仍是 AgenticOS-owned ROS2 bridge/HAL source。

---

## 1. 目标

### 1.1 用户体验目标

最终用户入口应该是：

```bash
/opt/agentic/bin/agentic
```

进入自然语言交互：

```text
AgenticOS ready.
agentic> 拍一张工作区照片
agentic> 从中间、左边、右边、上面拍照并验证差异
agentic> 查看最近照片
agentic> 停止机器人
agentic> 退出
```

也应该支持单行命令：

```bash
/opt/agentic/bin/agentic "拍一张工作区照片"
/opt/agentic/bin/agentic --real "拍一张工作区照片"
/opt/agentic/bin/agentic --real --allow-arm-motion --yes "从中间、左边、右边、上面拍照并验证差异"
```

旧入口可以保留为兼容和调试入口：

```bash
/opt/agentic/bin/agentic photo --real "拍一张照片"
/opt/agentic/bin/agentic chat --real
/opt/agentic/bin/agenticctl status --real
```

但产品心智应从：

```text
用户选择命令/选择 App
```

变成：

```text
用户描述目标 -> AgenticOS 调度 -> 选择 App -> 执行
```

### 1.2 系统目标

新增一个系统级调度 Agent：

```text
Agentic Dispatcher Agent
```

职责：

1. 接收自然语言任务。
2. 读取 App Registry / App Manifest。
3. 生成 OS 级 `task_route_plan`。
4. 校验 plan schema、权限、风险等级、确认策略。
5. 选择一个具体 Agent App。
6. 调用 Runtime/AppManager 启动该 App。
7. 聚合 App result、session、audit、storage output。

调度 Agent 不做的事情：

- 不 import `rclpy`。
- 不直接调用 ROS2。
- 不直接调用相机、机械臂、导航、底盘、MoveIt、Nav2。
- 不直接执行机器人能力。
- 不把 LLM 输出直接变成硬件动作。

---

## 2. 当前状态

当前 `/opt/agentic/bin/agentic` 已经有入口雏形：

```bash
if [ "$#" -eq 0 ]; then
  python -m agentic_runtime.nl_cli
fi
```

当前问题是：

1. `nl_cli.py` 还是规则分发，不是正式调度 Agent。
2. 相机/拍照类任务当前旧逻辑会路由到 `camera_arm_inspection_agent`，而不是优先使用更完整的 `robot_photographer_agent`。
3. `photo_cli.py` 作为专用入口已经能正确调用 `robot_photographer_agent`，但它不是通用自然语言入口。
4. AppManager 当前主要支持 legacy `main:run(ctx, **kwargs)` 形态；Robot Photographer 是 AIOS-compatible package，有 `entry.py` / `RobotPhotographerAgent.run(task_input)`，需要统一纳入通用 App 调用路径。

当前 App 工作区：

```text
/home/ubuntu/agentic_ws/src
  agentic_runtime_src
  app_template
  robot_photographer_agent
  inspection_agent
  camera_arm_inspection_agent
  room_inspection_app
```

当前已归档无关 scaffold apps：

```text
/home/ubuntu/agentic_ws/archived_unused_apps_20260615
  laundry_agent
  pickup_agent
  robotic_coding_agent
  robotops_agent
```

下一阶段自然语言调度应优先把拍照相关任务交给：

```text
robot_photographer_agent
```

而不是旧的 `camera_arm_inspection_agent`。

---

## 3. 总体架构

目标链路：

```text
User natural language
  -> /opt/agentic/bin/agentic
  -> Agentic Natural Language Gateway
  -> Dispatcher Agent
  -> OS-level bounded task_route_plan
  -> route plan schema validation
  -> route policy validation
  -> risk classification
  -> confirmation gate
  -> App invocation
  -> selected Agent App
  -> App-level planner / validation / deterministic executor
  -> AgenticOS SDK / system calls
  -> Runtime permission / resource lock / safety / audit
  -> ROS2 Bridge / HAL
  -> robot hardware
```

其中有两层 plan：

```text
第一层：OS route plan
  谁来做？
  是否允许做？
  是否需要确认？
  调哪个 Agent App？

第二层：App domain plan
  具体 App 内部怎么做？
  例如 Robot Photographer 的 photo_plan。
```

这两层不能合并。原因：

- 调度 Agent 只负责选择 App，不负责具体硬件动作。
- App 负责自己的领域 plan，但仍必须通过 Runtime safety。
- 即使调度 Agent 用 LLM，LLM 也只能输出 bounded JSON route plan。
- 即使 App planner 用 LLM，LLM 也只能输出 bounded JSON app plan。

---

## 4. 分层职责

### 4.1 Natural Language Gateway

位置建议：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/nl_gateway.py
```

安装后：

```text
/opt/agentic/lib/python3/agentic_runtime/nl_gateway.py
```

职责：

- 处理 CLI 参数。
- 进入交互模式。
- 处理 `退出`、Ctrl-C、EOF。
- 处理 `--real`、`--mock`、`--json`、`--allow-arm-motion`、`--yes` 等通用 flag。
- 创建 RuntimeServer。
- 把用户输入交给 Dispatcher Agent。

它不负责：

- App 路由逻辑。
- LLM prompt。
- 机器人 capability 调用。

### 4.2 Dispatcher Agent

位置建议：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/dispatcher/
  __init__.py
  agent.py
  planner.py
  validation.py
  executor.py
  app_index.py
  schemas/
    task_route_plan.schema.json
    dispatch_result.schema.json
  prompts/
    dispatcher.system.md
```

安装后：

```text
/opt/agentic/lib/python3/agentic_runtime/dispatcher/
```

调度 Agent 是 AgenticOS system agent，不是普通 App。

它可以读：

- App Registry。
- App `config.json`。
- App `app.yaml`。
- Runtime status。
- Session summary。
- Audit summary。

它不能直接调用：

- `ctx.robot.navigate_to`
- `ctx.perception.capture_photo`
- `ctx.arm.move_named`
- ROS2 topic/service/action

它唯一能做的执行动作是：

```text
Runtime/AppManager.run_app(selected_app_id, app_task_input)
```

### 4.3 Agent App

Agent App 仍然是可加载、可运行、可发布的 agent package。

以 Robot Photographer 为例：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/
  config.json
  app.yaml
  entry.py
  main.py
  planner.py
  validation.py
  verifier.py
  schemas/
  policies/
  prompts/
  workflows/
  storage/
  tests/
```

App 的职责：

- 处理自己的领域任务。
- 将自然语言或结构化 task input 转成 App-level bounded plan。
- 执行 App-level schema validation / policy validation。
- 通过 AgenticOS SDK 调用 system calls。
- 保存自己的用户产物到 App storage。

App 不得：

- 直接控制硬件。
- 直接 import ROS。
- 直接访问 ROS topic/service/action。

---

## 5. OS Route Plan Schema

新增 schema：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/dispatcher/schemas/task_route_plan.schema.json
```

建议结构：

```json
{
  "schema_version": "1.0",
  "task_id": "task_...",
  "user_text": "拍一张工作区照片",
  "planner_mode": "llm",
  "intent": "capture_photo",
  "selected_app_id": "robot_photographer_agent",
  "route_reason": "用户请求拍照，Robot Photographer 是摄影任务的 owner app",
  "risk_class": "read_only",
  "requires_robot_motion": false,
  "needs_confirmation": false,
  "target": "workspace",
  "app_task_input": {
    "text": "拍一张工作区照片",
    "mock": false,
    "allow_arm_motion": false,
    "assume_yes": false
  },
  "preflight_checks": [
    {
      "type": "app_available",
      "app_id": "robot_photographer_agent"
    },
    {
      "type": "capabilities_available",
      "capabilities": [
        "perception.capture_photo"
      ]
    }
  ],
  "fallback": {
    "mode": "rule_based",
    "reason": ""
  },
  "task_log": {
    "enabled": true,
    "retain_recent_n": 200
  },
  "user_summary": "使用 Robot Photographer 拍摄一张工作区照片"
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `schema_version` | route plan schema 版本 |
| `task_id` | 调度任务 ID |
| `user_text` | 原始用户输入 |
| `planner_mode` | `llm` 或 `rule_based` |
| `intent` | OS 层意图 |
| `selected_app_id` | 被选中的 Agent App |
| `route_reason` | 为什么选择这个 App |
| `risk_class` | `read_only` / `named_motion` / `navigation` / `emergency_control` / `unsupported` |
| `requires_robot_motion` | 是否需要机器人运动 |
| `needs_confirmation` | 是否需要用户确认 |
| `target` | 目标对象/地点，MVP 只允许已知 target |
| `app_task_input` | 传给具体 App 的输入 |
| `preflight_checks` | 执行前必须检查的条件 |
| `fallback` | LLM 不可用或输出非法时的 fallback 信息 |
| `task_log` | 是否写入 Dispatcher task 总账及 retention 提示 |
| `user_summary` | 给用户看的计划摘要 |

---

## 6. OS-level Intent

MVP 支持这些 OS 层 intent：

```text
capture_photo
multi_angle_photo
recent_photos
robot_status
robot_stop
room_inspection
unsupported
```

后续再扩展：

```text
object_pickup
laundry_task
robot_ops
coding_task
navigation_task
```

当前路由建议：

| 用户输入 | OS intent | selected_app_id |
|---|---|---|
| `拍一张照片` | `capture_photo` | `robot_photographer_agent` |
| `拍一组多角度照片` | `multi_angle_photo` | `robot_photographer_agent` |
| `查看最近照片` | `recent_photos` | `robot_photographer_agent` |
| `停止机器人` | `robot_stop` | built-in stop executor 或 `robot_photographer_agent` stop |
| `查看状态` | `robot_status` | built-in status executor |
| `检查厨房` | `room_inspection` | `inspection_agent`，如果启用 |
| `向下拍一张` | `unsupported` | none |
| `移动到底盘去门口` | `unsupported`，直到导航 App 安全上线 | none |

MVP 中，拍照相关任务必须优先路由到 `robot_photographer_agent`。

---

## 7. App Registry 与 App 能力索引

调度 Agent 不能靠硬编码字符串长期维护 App 路由。需要一个 App Index。

### 7.1 读取来源

每个 App 的：

```text
config.json
app.yaml
```

例如 Robot Photographer：

```json
{
  "name": "robot_photographer_agent",
  "description": "A real-robot photography Agent App running on AgenticOS...",
  "tools": [
    "agenticos/perception_capture_photo",
    "agenticos/arm_move_named",
    "agenticos/robot_stop",
    "agenticos/robot_status",
    "agenticos/recent_photos"
  ],
  "build": {
    "entry": "entry.py",
    "module": "RobotPhotographerAgent"
  }
}
```

### 7.2 推荐新增 `dispatch` 字段

后续建议给 `config.json` 增加：

```json
{
  "dispatch": {
    "enabled": true,
    "priority": 100,
    "intents": [
      "capture_photo",
      "multi_angle_photo",
      "recent_photos",
      "robot_status",
      "robot_stop"
    ],
    "keywords_zh": [
      "拍照",
      "照片",
      "相机",
      "图片",
      "多角度",
      "最近照片"
    ],
    "keywords_en": [
      "photo",
      "camera",
      "picture",
      "multi-angle"
    ],
    "risk_classes": [
      "read_only",
      "named_motion",
      "emergency_control"
    ],
    "default_target": "workspace"
  }
}
```

### 7.3 生成 App Index

运行时生成：

```json
{
  "apps": [
    {
      "app_id": "robot_photographer_agent",
      "description": "...",
      "dispatch_enabled": true,
      "intents": [
        "capture_photo",
        "multi_angle_photo",
        "recent_photos"
      ],
      "required_capabilities": [
        "perception.capture_photo",
        "arm.move_named",
        "storage.list_recent_photos"
      ],
      "permissions": [
        "perception.capture",
        "arm.move.named",
        "storage.read"
      ],
      "allowed_targets": [
        "workspace"
      ],
      "allowed_arm_actions": [
        "camera_center",
        "camera_yaw_left_15",
        "camera_yaw_right_15",
        "camera_pitch_up_15",
        "arm_home"
      ]
    }
  ]
}
```

调度 Agent 的 LLM prompt 只能看到这个 App Index 的摘要，而不是任意文件系统。

---

## 8. Dispatcher Planner

### 8.1 LLM-first + Rule Fallback

调度 Agent 可以使用 LLM，但必须是 bounded JSON 输出。

流程：

```text
user_text
  -> build dispatcher prompt
  -> LLM returns task_route_plan JSON object
  -> strict JSON parse
  -> schema validation
  -> route policy validation
  -> if invalid: rule fallback
  -> if fallback invalid: structured error
```

不能接受：

- Markdown fenced JSON。
- 工具调用文本。
- Python 代码。
- shell 命令。
- ROS topic/service/action 名称。
- 任意硬件动作。

### 8.2 Rule Fallback

规则 fallback 必须覆盖 MVP 高频路径：

```text
照片 / 拍照 / 相机 / 图片 / 多角度 / 最近照片
  -> robot_photographer_agent

停止 / 急停 / cancel / stop
  -> built-in stop

状态 / status
  -> built-in status

检查厨房 / 巡检
  -> inspection_agent，前提是该 app dispatch enabled

向下拍 / pitch down
  -> unsupported
```

### 8.3 Prompt 约束

`dispatcher.system.md` 核心约束：

```text
You are the AgenticOS Dispatcher Agent.
You only output one JSON object matching task_route_plan.schema.json.
You do not call tools.
You do not control hardware.
You do not invent apps or capabilities.
You select exactly one app_id or unsupported.
You must preserve robot safety boundaries.
If the request requires arbitrary joints, Cartesian trajectory, direct ROS, base movement, unverified pitch down, grabbing, or simulation, return unsupported.
```

---

## 9. Dispatcher Validation

调度 Agent 输出必须经过 validation。

校验项：

1. JSON object。
2. schema_version 正确。
3. `selected_app_id` 存在于 App Registry。
4. selected app `dispatch.enabled == true`。
5. intent 在 selected app 支持列表中。
6. required capabilities 已安装。
7. App permissions 不超过 app.yaml 声明。
8. target 在 App allowlist 中。
9. risk_class 与 task/app input 匹配。
10. 如果需要机械臂运动，必须有 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` 或 CLI `--allow-arm-motion`。
11. 如果需要机械臂运动，交互模式必须确认，除非 `--yes`。
12. 不允许调度 Agent 输出 ROS topic/service/action。
13. 不允许调度 Agent 输出任意关节目标、笛卡尔轨迹、自由抓取、底盘移动。
14. 不允许调度到 disabled/archived App。
15. `camera_pitch_down_15` 不允许出现在 route plan 或 app_task_input 中。

错误码建议：

```text
DISPATCH_PLAN_INVALID
DISPATCH_APP_NOT_FOUND
DISPATCH_APP_DISABLED
DISPATCH_INTENT_UNSUPPORTED
DISPATCH_TARGET_NOT_ALLOWED
DISPATCH_CAPABILITY_UNAVAILABLE
DISPATCH_MOTION_DISABLED
DISPATCH_CONFIRMATION_REQUIRED
DISPATCH_UNSAFE_REQUEST_REJECTED
DISPATCH_LLM_OUTPUT_INVALID_JSON
DISPATCH_LLM_SCHEMA_INVALID
DISPATCH_NO_ROUTE
```

---

## 10. Dispatcher Executor

Dispatcher executor 只执行这几种 step：

```text
validate_app
preflight_status
request_confirmation
run_app
return_result
```

其中只有 `run_app` 会进入具体 App。

伪代码：

```python
class DispatcherAgent:
    async def arun(self, user_text, flags):
        app_index = AppIndex.load()
        plan = planner.plan(user_text, app_index, flags)
        validated = validate_route_plan(plan, app_index, flags)

        if validated["selected_app_id"] == "builtin.status":
            return await builtins.status()

        if validated["selected_app_id"] == "builtin.stop":
            return await builtins.stop()

        if validated["needs_confirmation"] and not flags.assume_yes:
            return confirmation_required(validated)

        return await app_invoker.run(
            app_id=validated["selected_app_id"],
            task_input=validated["app_task_input"],
            parent_session_id=validated["task_id"],
        )
```

Dispatcher executor 不直接调用：

```text
ctx.perception.capture_photo
ctx.arm.move_named
ctx.robot.navigate_to
```

这些只能由被选中的 Agent App 通过 SDK/system call 调用。

---

## 11. App Invocation 统一

当前有两类 App：

### 11.1 Legacy AgenticOS App

```yaml
entrypoint: main:run
```

调用形态：

```python
await main.run(ctx, **kwargs)
```

例如：

```text
inspection_agent
room_inspection_app
camera_arm_inspection_agent
```

### 11.2 AIOS-compatible Agent Package

```yaml
runtime_type: aios_agent_package
aios_entrypoint: entry:RobotPhotographerAgent
executor_entrypoint: main:execute_plan
```

调用形态：

```python
agent = RobotPhotographerAgent(runtime=server, mock=mock)
await agent.arun(task_input)
```

例如：

```text
robot_photographer_agent
```

### 11.3 需要统一的 AppInvoker

新增：

```text
agentic_runtime/app_invoker.py
```

职责：

```text
if runtime_type == "aios_agent_package":
  load aios_entrypoint class
  call arun(task_input)
else:
  use legacy AppManager main:run(ctx, **kwargs)
```

这样 Dispatcher Agent 不需要知道某个 App 是新形态还是旧形态。

---

## 12. Session 与 Audit 关系

自然语言入口会产生两层 session：

```text
dispatcher_session
  app_session
```

建议 session metadata：

```json
{
  "session_id": "sess_dispatch_...",
  "app_id": "agentic_dispatcher",
  "child_session_ids": [
    "sess_robot_photographer_..."
  ],
  "route_plan_id": "task_...",
  "selected_app_id": "robot_photographer_agent"
}
```

App session metadata：

```json
{
  "session_id": "sess_robot_photographer_...",
  "app_id": "robot_photographer_agent",
  "parent_session_id": "sess_dispatch_...",
  "route_plan_id": "task_..."
}
```

Audit 应记录：

- 用户自然语言输入 hash 或原文，视隐私策略。
- route plan。
- selected app。
- confirmation result。
- App result summary。
- child session id。
- App storage path。
- raw evidence path。

---

## 12.5 Dispatcher Task Log

还需要新增一份 OS 级 task 日志。它不是 App 的详细执行日志，也不是 raw audit 的替代品，而是 Dispatcher 层的“任务总账”。

它回答这些问题：

- 用户提出了什么 task？
- Dispatcher 为这个 task 生成了什么 route plan？
- 具体安排了哪些 Agent / App 去完成？
- 每个 Agent / App 的 session id 是什么？
- 最终 task 成功、失败、取消还是被拒绝？
- 结果摘要是什么？
- 详细证据应该去哪里看？

它不记录：

- 每一步硬件 system call 的完整细节。
- 大图片、大视频、大模型上下文。
- Agent 内部完整推理轨迹。
- ROS topic payload。

这些详细内容应由具体 Agent App、Runtime session、audit、App storage、raw evidence 记录。

### 12.5.1 存储位置

建议新增：

```text
/opt/agentic/var/tasks/
  task_log.jsonl
  recent_tasks.json
  task_log.meta.json
```

源码实现位置：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/task_log/
  __init__.py
  manager.py
  models.py
  retention.py
```

安装后：

```text
/opt/agentic/lib/python3/agentic_runtime/task_log/
```

其中：

- `task_log.jsonl`：append-only task summary log。
- `recent_tasks.json`：最近 N 个 task 的快速索引。
- `task_log.meta.json`：记录 retention 配置、压缩时间、写入计数。

### 12.5.2 为什么不是 App storage

Task Log 属于 AgenticOS Dispatcher / OS 层，不属于某一个 App。

例如用户输入：

```text
拍一组多角度照片，然后告诉我结果
```

当前可能只调度：

```text
robot_photographer_agent
```

但未来可能调度：

```text
robot_photographer_agent
report_agent
memory_agent
```

所以 task log 必须在 OS 层统一保存。每个 App 只保存自己的执行产物和细节。

关系如下：

```text
/opt/agentic/var/tasks/task_log.jsonl
  记录 task 总账
  指向 dispatcher_session
  指向 child app sessions
  指向 app storage / raw evidence / audit ids

/opt/agentic/var/sessions/<session_id>/
  记录 Runtime session 和 syscalls

/opt/agentic/var/audit/audit.jsonl
  记录 capability/system-call 审计

/home/ubuntu/agentic_ws/src/<agent_app>/storage/
  记录 App 自己的用户产物和细节
```

### 12.5.3 Task Record Schema

建议 task record：

```json
{
  "schema_version": "1.0",
  "task_id": "task_20260616_000001",
  "created_at": "2026-06-16T00:00:01+08:00",
  "updated_at": "2026-06-16T00:00:08+08:00",
  "status": "completed",
  "user_text": "拍一张工作区照片",
  "user_text_hash": "sha256:...",
  "privacy_mode": "store_text",
  "dispatcher_session_id": "sess_dispatch_...",
  "route_plan_id": "plan_route_...",
  "planner_mode": "llm",
  "selected_app_id": "robot_photographer_agent",
  "selected_agents": [
    {
      "agent_id": "robot_photographer_agent",
      "role": "primary_executor",
      "reason": "photography task owner",
      "session_id": "sess_...",
      "status": "completed"
    }
  ],
  "risk_class": "read_only",
  "requires_robot_motion": false,
  "needs_confirmation": false,
  "confirmation": {
    "required": false,
    "granted": false,
    "source": ""
  },
  "result_summary": {
    "success": true,
    "error_code": "",
    "summary": "拍摄一张工作区照片",
    "app_output_paths": [
      "/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/runs/sess_.../photos/01_photo.png"
    ],
    "raw_evidence_paths": [
      "/opt/agentic/var/evidence/photos/photo_....png"
    ],
    "audit_ids": [
      "audit_..."
    ]
  },
  "detail_refs": {
    "route_plan_path": "/opt/agentic/var/tasks/plans/plan_route_....json",
    "dispatcher_session_path": "/opt/agentic/var/sessions/sess_dispatch_...",
    "app_session_paths": [
      "/opt/agentic/var/sessions/sess_..."
    ],
    "app_storage_paths": [
      "/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/runs/sess_..."
    ],
    "audit_log_path": "/opt/agentic/var/audit/audit.jsonl"
  }
}
```

`status` 枚举：

```text
planned
running
completed
failed
rejected
cancelled
partial
```

### 12.5.4 selected_agents 与多 Agent 调度

MVP 可以只支持一个 primary Agent：

```json
[
  {
    "agent_id": "robot_photographer_agent",
    "role": "primary_executor",
    "session_id": "sess_...",
    "status": "completed"
  }
]
```

但 schema 应提前支持多个 Agent：

```json
[
  {
    "agent_id": "robot_photographer_agent",
    "role": "primary_executor",
    "session_id": "sess_photo_...",
    "status": "completed"
  },
  {
    "agent_id": "report_agent",
    "role": "summary_writer",
    "session_id": "sess_report_...",
    "status": "completed"
  }
]
```

调度方式可以分阶段：

1. MVP：单 Agent route。
2. Phase 2：串行 multi-agent route。
3. Phase 3：带依赖 DAG 的 multi-agent route。

但真实机器人动作仍然只能由具体 App 通过 Runtime safety 执行，不能由 Dispatcher 或多个 Agent 抢资源。

### 12.5.5 Retention：只保留最近 N 个 task

考虑存储限制，Task Log 应有 retention 策略。

配置建议：

```yaml
task_log:
  enabled: true
  root: /opt/agentic/var/tasks
  retain_recent_n: 200
  retain_failed_n: 50
  retain_rejected_n: 50
  max_task_log_bytes: 10485760
  store_user_text: true
  hash_user_text: true
  compact_on_startup: true
```

策略：

1. `recent_tasks.json` 只保留最近 `retain_recent_n` 条。
2. `task_log.jsonl` 超过 `max_task_log_bytes` 时进行 compact。
3. compact 后保留：
   - 最近 N 条 task。
   - 最近 failed N 条。
   - 最近 rejected N 条。
   - 仍被 active session 引用的 task。
4. 大文件不进入 task log，只保存路径引用。
5. App 详情仍由 App storage 自己做 retention。

### 12.5.6 TaskLogManager API

建议 Runtime 内部 API：

```python
class TaskLogManager:
    def create_task(user_text, route_plan, dispatcher_session_id) -> TaskRecord:
        ...

    def mark_running(task_id, selected_agents) -> TaskRecord:
        ...

    def attach_agent_session(task_id, agent_id, session_id, role) -> TaskRecord:
        ...

    def complete_task(task_id, result_summary, detail_refs) -> TaskRecord:
        ...

    def fail_task(task_id, error_code, reason, detail_refs) -> TaskRecord:
        ...

    def reject_task(task_id, error_code, reason, route_plan) -> TaskRecord:
        ...

    def list_recent(limit=20) -> list[TaskRecord]:
        ...

    def compact() -> TaskLogRetentionReport:
        ...
```

CLI 对应：

```bash
/opt/agentic/bin/agenticctl tasks --limit 20
/opt/agentic/bin/agenticctl task <task_id>
```

自然语言：

```text
agentic> 最近任务
agentic> 上一个任务的结果
```

应路由到 TaskLogManager，而不是某个 App。

### 12.5.7 Dispatcher 执行中的写入时机

完整写入流程：

```text
用户输入
  -> TaskLogManager.create_task(status=planned)
  -> Dispatcher planner 生成 route_plan
  -> validation 通过
  -> TaskLogManager.mark_running(selected_agents=[...])
  -> AppInvoker.run_app(...)
  -> TaskLogManager.attach_agent_session(...)
  -> App 返回 result
  -> TaskLogManager.complete_task(...) 或 fail_task(...)
```

如果任务在 Dispatcher 层被拒绝：

```text
用户输入
  -> create_task(status=planned)
  -> validation rejected
  -> reject_task(status=rejected, error_code=...)
```

### 12.5.8 与 Audit 的边界

Task Log 是“索引和摘要”。

Audit 是“不可跳过的执行证据”。

两者关系：

```text
Task Log:
  task_id
  selected_agents
  final status
  result summary
  refs

Audit:
  permission_result
  safety_result
  resource_lock_result
  backend
  syscall result
```

Task Log 可以删除旧 task 摘要，但 audit retention 由系统审计策略单独控制。真实机器人事故排查时，audit 的保留策略应该比 task log 更严格。

---

## 13. CLI 设计

### 13.1 `/opt/agentic/bin/agentic`

建议改造：

```bash
agentic
  -> python -m agentic_runtime.nl_gateway

agentic "拍一张照片"
  -> python -m agentic_runtime.nl_gateway "拍一张照片"

agentic --real "拍一张照片"
  -> real mode

agentic --mock "拍一张照片"
  -> mock mode

agentic photo ...
  -> legacy/debug shortcut, still supported

agenticctl ...
  -> operator/admin commands
```

### 13.2 推荐参数

```text
--real
--mock
--json
--allow-arm-motion
--yes
--show-plan
--dry-run
--app <app_id>        可选，强制指定 App，主要用于调试
--no-llm             强制 rule fallback
--tasks-limit <n>    查看最近任务时的返回数量
```

### 13.3 示例

只读拍照：

```bash
/opt/agentic/bin/agentic --real "拍一张工作区照片"
```

显示计划但不执行：

```bash
/opt/agentic/bin/agentic --real --show-plan --dry-run "拍一组多角度照片"
```

允许真实机械臂动作：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
/opt/agentic/bin/agentic --real --allow-arm-motion --yes \
"从中间、左边、右边、上面拍照并验证差异"
```

查看最近照片：

```bash
/opt/agentic/bin/agentic --real "最近照片"
```

停止：

```bash
/opt/agentic/bin/agentic --real "停止机器人"
```

查看最近任务总账：

```bash
/opt/agentic/bin/agentic "最近任务"
/opt/agentic/bin/agenticctl tasks --limit 20
```

查看上一个任务结果：

```bash
/opt/agentic/bin/agentic "上一个任务的结果"
```

---

## 14. Robot Photographer 路由细节

对于 Robot Photographer，Dispatcher route plan 应只传自然语言和通用 flag：

```json
{
  "selected_app_id": "robot_photographer_agent",
  "app_task_input": {
    "text": "从中间、左边、右边、上面拍照并验证差异",
    "mock": false,
    "allow_arm_motion": true,
    "assume_yes": true
  }
}
```

Dispatcher 不应该直接构造 photo_plan。

原因：

- Robot Photographer 内部已经有 `planner.py`。
- Robot Photographer 内部已经知道自己的 schema/policy。
- Dispatcher 不应该拥有 App 领域细节。

Robot Photographer 内部仍执行：

```text
task_input
  -> RobotPhotographerAgent.run/arun
  -> planner.py
  -> photo_plan.schema.json
  -> policy validation
  -> confirmation gate
  -> deterministic executor
  -> AgenticOS SDK/system calls
```

---

## 15. Built-in OS Commands

不是所有自然语言都必须路由到 App。

这些可以作为 built-in system command：

```text
status
sessions
audit
tasks
last_task
help
stop
exit
```

设计建议：

| 自然语言 | executor |
|---|---|
| `查看状态` | Runtime status |
| `最近会话` | SessionManager |
| `最近审计` | AuditLogger |
| `最近任务` | TaskLogManager |
| `上一个任务的结果` | TaskLogManager |
| `帮助` | NL Gateway help |
| `停止机器人` | Runtime `robot.stop` system call through safety path |

注意：`stop` 虽然是 built-in，也必须走 Runtime/bridge，不允许 CLI 直接发布 ROS stop topic。

---

## 16. 安全策略

### 16.1 双层安全门

真实机器人动作必须经过两层门：

```text
Dispatcher route validation
  -> App plan validation
  -> Runtime permission/resource/safety/audit
```

即使 Dispatcher 判断可执行，App 仍然可以拒绝。

即使 App 判断可执行，Runtime 仍然可以拒绝。

### 16.2 Motion Gate

机械臂动作必须满足：

```text
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1
或 CLI --allow-arm-motion
```

并且交互模式需要确认，除非：

```text
--yes
```

### 16.3 禁止项

Dispatcher 和 App 都必须拒绝：

- 任意关节目标。
- 笛卡尔轨迹。
- 自由抓取。
- 底盘移动，除非专门导航 App 安全上线。
- Gazebo/gz/fake Nav2/RViz-only demo。
- `camera_pitch_down_15`，直到有真实验证过的安全后端。
- `left_down.d6a` / `right_down.d6a` 作为 camera pose。
- 直接 ROS topic/service/action。

---

## 17. 实现顺序

推荐实现顺序：

1. 新增 Dispatcher 设计目录和 schema。
2. 新增 App Index 生成器，读取 `config.json` 和 `app.yaml`。
3. 给 `robot_photographer_agent/config.json` 增加 `dispatch` 字段。
4. 实现 rule-based dispatcher planner。
5. 实现 dispatcher route validation。
6. 实现 TaskLogManager，支持 create/running/complete/fail/reject/list_recent/compact。
7. 实现 AppInvoker，统一 legacy app 和 AIOS-compatible app。
8. 新增 `nl_gateway.py`，替换当前 `nl_cli.py` 的硬编码路由。
9. 修改 `/opt/agentic/bin/agentic` 安装脚本逻辑：默认自然语言入口。
10. 接入 LLM-first dispatcher planner，rule fallback 保底。
11. 增加 `--show-plan` 和 `--dry-run`。
12. 增加 session/audit/task-log parent-child correlation。
13. 增加 `agenticctl tasks` 和 `agenticctl task <task_id>`。
14. 更新 tests。
15. 安装到 `/opt/agentic`。
16. 跑 mock 和真实只读验证。
17. 最后再跑可选真实机械臂动作验证。

---

## 18. 测试要求

必须新增或更新：

```text
tests/test_dispatcher_plan_schema.py
tests/test_dispatcher_routes_robot_photographer.py
tests/test_dispatcher_rejects_unknown_app.py
tests/test_dispatcher_rejects_unsafe_motion.py
tests/test_dispatcher_motion_confirmation.py
tests/test_dispatcher_no_direct_ros.py
tests/test_app_invoker_aios_package.py
tests/test_app_invoker_legacy_app.py
tests/test_task_log_manager.py
tests/test_task_log_retention.py
tests/test_dispatcher_writes_task_log.py
tests/test_nl_gateway_cli.py
tests/test_agentic_default_entrypoint.py
```

测试场景：

1. `拍一张照片` -> `robot_photographer_agent`。
2. `拍一组多角度照片并验证差异` -> `robot_photographer_agent`。
3. `最近照片` -> `robot_photographer_agent`。
4. `向下拍一张` -> unsupported。
5. `用 /servo_controller 动一下机械臂` -> unsafe rejected。
6. 未设置 motion env 时，多角度真实动作需要拒绝。
7. 设置 motion env 但没有 `--yes` 时，需要 confirmation。
8. 每个自然语言 task 都写入 task log。
9. task log 记录 selected agents、child session、final status、result summary、detail refs。
10. task log 不保存大图片/视频，只保存路径引用。
11. retention 只保留最近 N 个 task，并保留最近 failed/rejected task。
12. `最近任务` 返回 TaskLogManager 的 recent task index。
13. `上一个任务的结果` 返回最近 task 的 result summary 和 detail refs。
14. `--show-plan --dry-run` 只输出 route plan，不执行 App，但仍可以写入 dry-run/rejected task 记录。
15. Dispatcher 不 import `rclpy`。
16. Dispatcher 不包含 ROS topic/service/action 直接调用。
17. AppInvoker 能调用 Robot Photographer `entry.py`。
18. AppInvoker 仍能调用 legacy `main:run(ctx)` App。
19. `/opt/agentic/bin/agentic "拍一张照片"` 能工作。
20. `agentic photo` 作为兼容入口仍能工作。

---

## 19. 文件变更建议

新增：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/dispatcher/
  __init__.py
  agent.py
  app_index.py
  planner.py
  validation.py
  executor.py
  schemas/
    task_route_plan.schema.json
    dispatch_result.schema.json
  prompts/
    dispatcher.system.md

/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/task_log/
  __init__.py
  manager.py
  models.py
  retention.py

/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/nl_gateway.py
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/app_invoker.py
```

修改：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh
/home/ubuntu/agentic_ws/src/agentic_runtime_src/configs/runtime.yaml
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/nl_cli.py
/home/ubuntu/agentic_ws/src/robot_photographer_agent/config.json
/home/ubuntu/agentic_ws/src/agentic_runtime_src/tests/*
```

安装后同步：

```text
/opt/agentic/bin/agentic
/opt/agentic/lib/python3/agentic_runtime/dispatcher/
/opt/agentic/lib/python3/agentic_runtime/task_log/
/opt/agentic/lib/python3/agentic_runtime/nl_gateway.py
/opt/agentic/lib/python3/agentic_runtime/app_invoker.py
/opt/agentic/var/tasks/
```

---

## 20. MVP 行为示例

### 20.1 拍一张照片

输入：

```text
拍一张工作区照片
```

Dispatcher route plan：

```json
{
  "intent": "capture_photo",
  "selected_app_id": "robot_photographer_agent",
  "risk_class": "read_only",
  "requires_robot_motion": false,
  "needs_confirmation": false,
  "target": "workspace",
  "app_task_input": {
    "text": "拍一张工作区照片",
    "mock": false,
    "allow_arm_motion": false,
    "assume_yes": false
  }
}
```

App result：

```json
{
  "success": true,
  "app_image_path": "/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/runs/<session_id>/photos/01_photo.png",
  "raw_evidence_image_path": "/opt/agentic/var/evidence/photos/..."
}
```

### 20.2 多角度拍摄

输入：

```text
从中间、左边、右边、上面拍照并验证差异
```

Dispatcher：

```text
selected_app_id = robot_photographer_agent
risk_class = named_motion
requires_robot_motion = true
needs_confirmation = true
```

Robot Photographer 内部只允许：

```text
camera_center
camera_yaw_left_15
camera_yaw_right_15
camera_pitch_up_15
arm_home
```

不允许：

```text
camera_pitch_down_15
left_down.d6a
right_down.d6a
```

### 20.3 向下拍

输入：

```text
向下拍一张
```

输出：

```json
{
  "success": false,
  "error_code": "DISPATCH_UNSAFE_REQUEST_REJECTED",
  "reason": "向下俯仰拍摄暂不支持：尚未验证安全的 camera_pitch_down 后端动作"
}
```

也可以让 Dispatcher 路由到 Robot Photographer，由 Robot Photographer 返回：

```text
PHOTO_INTENT_UNSUPPORTED
```

MVP 建议在 Dispatcher 层提前拒绝，以减少不必要的 App 启动。

---

## 21. 与传统 OS 的类比

这个调度 Agent 类似桌面 OS 中的：

```text
Shell / Launcher / Intent Resolver
```

类比关系：

```text
用户自然语言
  -> Shell
  -> Intent Resolver
  -> 选择应用程序
  -> 应用程序调用系统 API
  -> Kernel / Driver
  -> Hardware
```

AgenticOS 中：

```text
用户自然语言
  -> Agentic Natural Language Gateway
  -> Dispatcher Agent
  -> 选择 Agent App
  -> Agent App 调用 AgenticOS SDK
  -> Runtime / Kernel permission + safety
  -> ROS2 Bridge / HAL
  -> Robot Hardware
```

所以调度 Agent 不是“万能机器人控制器”，而是“系统级任务入口和 App 启动器”。

---

## 22. 实现级补充规格

这一节把上面的架构设计进一步收敛成 Codex 可以直接实现的工程规格。实现时优先做 MVP，不要在第一版引入复杂多 Agent DAG、远程 App marketplace、Web UI 或新的机器人运动能力。

### 22.1 MVP 必须完成的闭环

MVP 完成后，下面这些命令应该可用：

```bash
/opt/agentic/bin/agentic --mock --json "拍一张照片"
/opt/agentic/bin/agentic --mock --json "最近照片"
/opt/agentic/bin/agentic --mock --json "最近任务"
/opt/agentic/bin/agentic --mock --json "上一个任务的结果"
/opt/agentic/bin/agentic --mock --json "向下拍一张"
/opt/agentic/bin/agentic --real --json "拍一张工作区照片"
/opt/agentic/bin/agenticctl tasks --limit 20
/opt/agentic/bin/agenticctl task <task_id>
```

其中：

- `拍一张照片` 必须路由到 `robot_photographer_agent`。
- `最近照片` 必须路由到 `robot_photographer_agent` 或 Runtime storage capability，但不能回到旧的 `camera_arm_inspection_agent`。
- `最近任务` 和 `上一个任务的结果` 必须由 Dispatcher/TaskLog 处理，不进入 Robot Photographer。
- `向下拍一张` 必须被结构化拒绝，不能触发 `pitch_down`、`left_down.d6a`、`right_down.d6a` 或任何抓取动作。
- `--show-plan --dry-run` 只能输出 route plan 和 task log dry-run 记录，不能调用 App executor。

MVP 中只允许单 Agent route：

```text
one user task -> one selected_app_id -> one app invocation
```

但 task log 和 schema 要为未来多 Agent 预留 `selected_agents[]`。

### 22.2 推荐实现目录

新增 Runtime 源码：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/
  nl_gateway.py
  app_invoker.py
  dispatcher/
    __init__.py
    agent.py
    app_index.py
    planner.py
    validation.py
    executor.py
    errors.py
    schemas/
      task_route_plan.schema.json
      dispatch_result.schema.json
    prompts/
      dispatcher.system.md
  task_log/
    __init__.py
    manager.py
    models.py
    retention.py
```

新增或更新测试：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/tests/
  test_dispatcher_plan_schema.py
  test_dispatcher_routes_robot_photographer.py
  test_dispatcher_rejects_unknown_app.py
  test_dispatcher_rejects_unsafe_motion.py
  test_dispatcher_motion_confirmation.py
  test_dispatcher_no_direct_ros.py
  test_dispatcher_task_log.py
  test_task_log_retention.py
  test_app_invoker_aios_package.py
  test_app_invoker_legacy_app.py
  test_nl_gateway_cli.py
  test_agentic_default_entrypoint.py
```

更新 Robot Photographer：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/config.json
```

给它增加 `dispatch` 字段，不改变它自己的 plan-first 架构。

更新安装脚本：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh
```

安装后应同步：

```text
/opt/agentic/lib/python3/agentic_runtime/nl_gateway.py
/opt/agentic/lib/python3/agentic_runtime/app_invoker.py
/opt/agentic/lib/python3/agentic_runtime/dispatcher/
/opt/agentic/lib/python3/agentic_runtime/task_log/
/opt/agentic/var/tasks/
```

### 22.3 `nl_gateway.py` 具体职责

`nl_gateway.py` 是默认 CLI 入口。它只处理交互、参数和输出格式，不做 route 决策。

建议函数：

```python
def build_parser() -> argparse.ArgumentParser:
    ...

def run_once(argv: list[str]) -> int:
    ...

def run_interactive(flags: GatewayFlags) -> int:
    ...

def dispatch_text(user_text: str, flags: GatewayFlags) -> DispatchResult:
    ...

def print_result(result: DispatchResult, *, as_json: bool) -> None:
    ...
```

`GatewayFlags` 建议字段：

```python
@dataclass
class GatewayFlags:
    real: bool
    mock: bool
    json: bool
    allow_arm_motion: bool
    assume_yes: bool
    show_plan: bool
    dry_run: bool
    no_llm: bool
    forced_app_id: str | None
    tasks_limit: int
```

参数语义：

| 参数 | 语义 |
|---|---|
| `--real` | 使用真实 Runtime/bridge 能力 |
| `--mock` | 使用 mock Runtime/bridge，测试默认可用 |
| `--json` | 输出结构化 JSON |
| `--allow-arm-motion` | 允许计划包含命名机械臂动作，但仍需 Runtime safety |
| `--yes` | 跳过交互确认 |
| `--show-plan` | 返回 route plan |
| `--dry-run` | 不执行 App |
| `--no-llm` | 强制 rule fallback |
| `--app <app_id>` | 调试用，强制候选 App，但仍需 validation |
| `--tasks-limit <n>` | 最近任务查询数量 |

交互模式内置命令：

```text
帮助
退出
最近任务
上一个任务的结果
最近会话
最近审计
查看状态
停止机器人
```

`停止机器人` 必须走 Runtime 的 stop capability 或现有安全路径，不能直接发布 ROS topic。

### 22.4 `DispatcherAgent` 具体接口

建议：

```python
class DispatcherAgent:
    def __init__(
        self,
        runtime,
        app_index: AppIndex,
        task_log: TaskLogManager,
        planner: DispatcherPlanner,
        validator: DispatcherValidator,
        executor: DispatcherExecutor,
    ) -> None:
        ...

    def run(self, user_text: str, flags: GatewayFlags) -> dict:
        ...
```

同步实现优先。若现有 Runtime/AppManager 是 async，再增加：

```python
async def arun(self, user_text: str, flags: GatewayFlags) -> dict:
    ...
```

`run()` 的步骤必须固定：

```text
1. normalize user_text
2. create dispatcher session
3. create task log record, status=planned
4. load AppIndex
5. planner creates task_route_plan
6. write route_plan JSON under /opt/agentic/var/tasks/plans/
7. validate schema/policy/risk/confirmation
8. if rejected, task_log.reject_task(...)
9. if dry-run, task_log.complete_task(status=dry_run) and return plan
10. if built-in command, execute built-in through safe Runtime API
11. if app route, task_log.mark_running(...)
12. AppInvoker.run_app(...)
13. attach child app session/result refs if available
14. task_log.complete_task(...) or fail_task(...)
15. return dispatch_result
```

Dispatcher 不允许调用这些接口：

```text
ctx.perception.capture_photo
ctx.arm.move_named
ctx.robot.navigate_to
ctx.robot.base_move
ROS2 topic/service/action
```

Dispatcher 只允许调用：

```text
AppInvoker.run_app(...)
TaskLogManager.*
SessionManager summary/list
Audit summary/list
Runtime status
Runtime stop safe wrapper
```

### 22.5 AppIndex 具体规则

`AppIndex` 扫描顺序：

```text
1. /home/ubuntu/agentic_ws/src/*/config.json
2. /home/ubuntu/agentic_ws/src/*/app.yaml
3. 可选：/opt/agentic/apps/*/config.json
```

MVP 可以只实现第 1 和第 2 项。

索引项建议：

```python
@dataclass
class AppIndexEntry:
    app_id: str
    root: str
    config_path: str | None
    app_yaml_path: str | None
    description: str
    runtime_type: str
    entrypoint: str | None
    aios_entrypoint: str | None
    dispatch_enabled: bool
    dispatch_priority: int
    intents: list[str]
    keywords_zh: list[str]
    keywords_en: list[str]
    risk_classes: list[str]
    required_capabilities: list[str]
    permissions: list[str]
    allowed_targets: list[str]
    allowed_arm_actions: list[str]
    archived: bool
```

AppIndex 必须忽略：

- 没有 `app.yaml` 且没有 `config.json` 的目录。
- archived 目录。
- `dispatch.enabled != true` 的 App，除非 CLI 使用 `--app` 调试且 validation 仍允许。
- `agentic_runtime_src` 和 `app_template`，它们不是可调度业务 App。

Robot Photographer 的 `config.json` 建议增加：

```json
{
  "dispatch": {
    "enabled": true,
    "priority": 100,
    "intents": [
      "capture_photo",
      "multi_angle_photo",
      "recent_photos",
      "robot_status",
      "robot_stop"
    ],
    "keywords_zh": [
      "拍照",
      "照片",
      "相机",
      "图片",
      "多角度",
      "最近照片"
    ],
    "keywords_en": [
      "photo",
      "camera",
      "picture",
      "multi-angle"
    ],
    "risk_classes": [
      "read_only",
      "named_motion",
      "emergency_control"
    ],
    "default_target": "workspace"
  }
}
```

### 22.6 Route Planner 细节

Planner 顺序：

```text
if flags.no_llm:
  use rule planner
else if AGENTIC_LLM_ENABLED=1 and LLM config available:
  try LLM planner
  if LLM invalid: rule fallback
else:
  rule fallback
```

LLM planner 只允许返回一个 JSON object。不得接受：

- markdown fence。
- JSON array。
- 带解释文本的 JSON。
- tool call。
- shell 命令。
- ROS topic/service/action 名称。

LLM 失败码：

```text
DISPATCH_LLM_DISABLED
DISPATCH_LLM_TIMEOUT
DISPATCH_LLM_NETWORK_ERROR
DISPATCH_LLM_OUTPUT_INVALID_JSON
DISPATCH_LLM_SCHEMA_INVALID
DISPATCH_LLM_POLICY_REJECTED
```

Rule fallback 必须覆盖：

| 关键词 | route |
|---|---|
| `拍照`、`照片`、`图片`、`相机` | `capture_photo` -> `robot_photographer_agent` |
| `多角度`、`中间`、`左边`、`右边`、`上面` | `multi_angle_photo` -> `robot_photographer_agent` |
| `最近照片`、`照片列表` | `recent_photos` -> `robot_photographer_agent` |
| `最近任务`、`任务记录` | built-in `tasks` |
| `上一个任务`、`上次结果` | built-in `last_task` |
| `状态`、`status` | built-in `robot_status` |
| `停止`、`急停`、`stop`、`cancel` | built-in `robot_stop` |
| `向下拍`、`pitch down`、`下方角度` | unsupported/rejected |
| `/cmd_vel`、`/tf`、`servo`、`MoveIt`、`Nav2` | unsafe rejected |

### 22.7 `task_route_plan.schema.json`

Schema 需要至少包含：

```json
{
  "schema_version": "1.0",
  "task_id": "task_...",
  "route_plan_id": "plan_route_...",
  "created_at": "2026-06-15T00:00:00Z",
  "user_text": "拍一张照片",
  "planner_mode": "rule_based",
  "intent": "capture_photo",
  "selected_app_id": "robot_photographer_agent",
  "route_reason": "photography task owner",
  "risk_class": "read_only",
  "requires_robot_motion": false,
  "needs_confirmation": false,
  "target": "workspace",
  "app_task_input": {
    "text": "拍一张照片",
    "mock": true,
    "allow_arm_motion": false,
    "assume_yes": false
  },
  "preflight_checks": [],
  "fallback": {
    "used": false,
    "reason": ""
  },
  "user_summary": "使用 Robot Photographer 拍摄一张照片"
}
```

枚举：

```text
intent:
  capture_photo
  multi_angle_photo
  recent_photos
  robot_status
  robot_stop
  tasks
  last_task
  help
  unsupported

selected_app_id:
  robot_photographer_agent
  builtin.status
  builtin.stop
  builtin.tasks
  builtin.last_task
  builtin.help
  unsupported

risk_class:
  read_only
  named_motion
  emergency_control
  unsupported

target:
  workspace
```

MVP 不加入 `navigation`，避免让自然语言入口误以为底盘导航已经安全上线。

### 22.8 Route Validation 细节

`validation.py` 建议暴露：

```python
def parse_strict_json_object(text: str) -> dict:
    ...

def validate_schema(plan: dict) -> None:
    ...

def validate_route_policy(plan: dict, app_index: AppIndex, flags: GatewayFlags) -> None:
    ...

def classify_risk(plan: dict) -> str:
    ...

def requires_confirmation(plan: dict, flags: GatewayFlags) -> bool:
    ...

def assert_no_direct_ros_references(plan: dict) -> None:
    ...
```

必须检查：

- `selected_app_id` 是否存在，built-in 除外。
- App 是否 `dispatch.enabled == true`。
- `intent` 是否在 App 支持列表内。
- `target == workspace`。
- `app_task_input` 中不能出现 ROS topic/service/action。
- `app_task_input` 中不能出现 `camera_pitch_down_15`、`left_down.d6a`、`right_down.d6a`。
- `requires_robot_motion == true` 时，必须有 env 或 CLI motion flag。
- motion task 如果没有 `--yes`，交互模式返回 `DISPATCH_CONFIRMATION_REQUIRED`。
- `--app` 强制指定时，也不能绕过 policy。

直接 ROS guard 建议扫描这些 forbidden patterns：

```text
rclpy
/cmd_vel
/scan
/odom
/tf
/camera
/servo
/servo_controller
/controller_manager
MoveIt
Nav2
kinematics
joint_trajectory
JointTrajectory
Cartesian
Gazebo
gz
RViz-only
```

错误结果必须结构化：

```json
{
  "success": false,
  "error_code": "DISPATCH_UNSAFE_REQUEST_REJECTED",
  "message": "Direct ROS or unsafe robot motion request is not allowed.",
  "task_id": "task_...",
  "selected_app_id": "unsupported"
}
```

### 22.9 AppInvoker 细节

`app_invoker.py` 统一 App 调用。

建议接口：

```python
class AppInvoker:
    def __init__(self, runtime, app_index: AppIndex) -> None:
        ...

    def run_app(
        self,
        app_id: str,
        task_input: dict,
        *,
        parent_session_id: str,
        route_plan_id: str,
    ) -> dict:
        ...
```

AIOS-compatible 调用：

```text
runtime_type == aios_agent_package
aios_entrypoint == entry:RobotPhotographerAgent
```

加载逻辑：

```python
root = app_entry.root
temporarily prepend root to sys.path
module = importlib.import_module("entry")
cls = getattr(module, "RobotPhotographerAgent")
agent = cls(runtime=runtime)
result = agent.run(task_input)
```

Legacy 调用：

```text
entrypoint == main:run
```

加载逻辑：

```python
module = importlib.import_module("main")
fn = getattr(module, "run")
result = fn(ctx, **task_input)
```

AppInvoker 必须：

- 传递 `parent_session_id` 和 `route_plan_id`。
- 捕获异常并返回结构化错误。
- 不 import `rclpy`。
- 不解析用户自然语言。
- 不替 App 构造领域 plan。
- 不改变 App policy。

### 22.10 TaskLogManager 实现细节

存储目录：

```text
/opt/agentic/var/tasks/
  task_log.jsonl
  recent_tasks.json
  task_log.meta.json
  plans/
    <route_plan_id>.json
```

开发测试时可通过环境变量覆盖：

```text
AGENTIC_TASK_LOG_ROOT=/tmp/agentic_test_tasks
```

写入要求：

- `task_log.jsonl` append-only。
- `recent_tasks.json` 原子写：先写 `recent_tasks.json.tmp`，再 rename。
- 单条 task record 不得保存图片、视频、base64、大模型上下文。
- 路径引用可以保存。
- 用户原文按配置保存；同时保存 `user_text_hash`。
- 写失败不能让机器人动作绕过 audit。写 task log 失败时，Dispatcher 应返回 `DISPATCH_TASK_LOG_WRITE_FAILED`，不要继续执行真实运动任务。

Task record 状态：

```text
planned
running
completed
failed
rejected
cancelled
dry_run
partial
```

保留策略：

```text
retain_recent_n: 200
retain_failed_n: 50
retain_rejected_n: 50
max_task_log_bytes: 10485760
```

compact 规则：

```text
1. 读取 task_log.jsonl。
2. 保留最近 retain_recent_n。
3. 额外保留最近 retain_failed_n 个 failed。
4. 额外保留最近 retain_rejected_n 个 rejected。
5. 去重后按 updated_at 排序。
6. 写 task_log.compacted.jsonl.tmp。
7. rename 为 task_log.jsonl。
8. 重建 recent_tasks.json。
9. 更新 task_log.meta.json。
```

### 22.11 DispatchResult 格式

统一返回：

```json
{
  "success": true,
  "status": "completed",
  "task_id": "task_...",
  "route_plan_id": "plan_route_...",
  "dispatcher_session_id": "sess_dispatch_...",
  "selected_app_id": "robot_photographer_agent",
  "selected_agents": [
    {
      "agent_id": "robot_photographer_agent",
      "role": "primary_executor",
      "session_id": "sess_...",
      "status": "completed"
    }
  ],
  "risk_class": "read_only",
  "requires_robot_motion": false,
  "needs_confirmation": false,
  "route_plan": {},
  "app_result": {},
  "result_summary": {
    "summary": "拍摄完成",
    "app_output_paths": [],
    "raw_evidence_paths": [],
    "audit_ids": []
  },
  "task_log_path": "/opt/agentic/var/tasks/task_log.jsonl"
}
```

失败返回：

```json
{
  "success": false,
  "status": "rejected",
  "error_code": "DISPATCH_UNSAFE_REQUEST_REJECTED",
  "message": "向下俯仰拍摄暂不支持。",
  "task_id": "task_...",
  "route_plan_id": "plan_route_...",
  "selected_app_id": "unsupported"
}
```

### 22.12 App Storage 与 Raw Evidence 的关系

Robot Photographer 的用户产物应放在 App storage：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage/
  runs/<app_session_id>/
    photos/
    videos/
    logs/
    result.json
```

Runtime raw evidence 仍可放在：

```text
/opt/agentic/var/evidence/photos/
```

两者边界：

- `/opt/agentic/var/evidence/photos` 是 OS/raw evidence，服务 audit、事故排查和 capability 证据。
- `robot_photographer_agent/storage` 是 App 用户产物，服务用户查看、App 内检索和发布。
- App result 应同时返回 `app_output_paths` 和 `raw_evidence_paths`。
- 如果 capability 只返回 raw evidence，Robot Photographer executor 应把图片复制或登记到自己的 `storage/runs/<session_id>/photos/`，不能只把用户指向 `/opt/agentic/var/evidence`。
- task log 只保存两类路径引用，不保存图片本体。

### 22.13 安装和兼容策略

安装脚本要保证：

```text
/opt/agentic/bin/agentic
```

默认进入：

```text
python -m agentic_runtime.nl_gateway
```

同时保留兼容子命令：

```text
agentic photo ...
agentic chat ...
agenticctl status ...
```

如果用户输入第一个参数是已知 legacy subcommand，就走旧入口：

```text
photo
chat
run
ctl
```

否则按自然语言处理。

### 22.14 验收标准

必须通过：

```bash
cd /home/ubuntu/agentic_ws/src/agentic_runtime_src
python scripts/check_forbidden_imports.py
scripts/run_tests.sh
pytest tests/test_dispatcher_plan_schema.py tests/test_dispatcher_routes_robot_photographer.py tests/test_task_log_retention.py
pytest /home/ubuntu/agentic_ws/src/robot_photographer_agent/tests
scripts/build_robot_bridge.sh
```

安装侧验证：

```bash
/opt/agentic/bin/agentic --mock --json "拍一张照片"
/opt/agentic/bin/agentic --mock --json "最近照片"
/opt/agentic/bin/agentic --mock --json "最近任务"
/opt/agentic/bin/agentic --mock --json "上一个任务的结果"
/opt/agentic/bin/agentic --mock --json "向下拍一张"
/opt/agentic/bin/agentic --mock --show-plan --dry-run --json "拍一组多角度照片"
/opt/agentic/bin/agenticctl tasks --limit 20
```

真实只读验证：

```bash
/opt/agentic/bin/agentic --real --json "拍一张工作区照片"
```

真实运动验证只能手动显式开启：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
/opt/agentic/bin/agentic --real --allow-arm-motion --yes --json \
"从中间、左边、右边、上面拍照并验证差异"
```

验收时必须检查：

- route plan 是否选择 `robot_photographer_agent`。
- task log 是否写入。
- task log 是否包含 selected_agents 和 child session。
- App output 是否进入 `robot_photographer_agent/storage`。
- raw evidence 是否保留 `/opt/agentic/var/evidence` 路径引用。
- `向下拍一张` 是否拒绝。
- 没有 `rclpy` import 泄漏。
- 没有直接 ROS topic/service/action 调用。

## 23. 最终判断

AgenticOS 的主入口应该是自然语言入口；但自然语言入口不应该直接等于“LLM 控制机器人”。

正确形态是：

```text
自然语言入口
  -> 系统级 Dispatcher Agent
  -> OS route plan
  -> OS task log
  -> 选择具体 Agent App
  -> App 自己的 plan-first 执行
  -> AgenticOS Runtime safety
  -> ROS2 Bridge/HAL
```

这样既符合 AIOS/Cerebrum 的 Agent App 思想，也保留 AgenticOS 对真实机器人的安全边界。
