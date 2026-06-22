# Agentic App 开发者指南

最后更新：2026-06-22

本文面向第一次开发 Agentic App 的开发者和本科生。读完本文后，你应该能够从模板创建一个自己的 Agentic App，写清楚权限、上下文、规划、规则校验、系统调用、记忆、存储、测试和 demo。

本文按 AgenticOS 的目标开发合同编写：假设 AgenticOS 系统调用接口是完整的。开发者不要因为某个本地环境暂时没有接上真实机器人、真实 bridge 或真实模型，就在产品代码里忽略接口、绕过接口、写本地 mock 后门，或者直接调用 ROS2。测试可以在 `tests/` 中使用 Fake Context 来验证 app 逻辑，但产品代码必须始终面向正式 `ctx.*` 系统调用编程。

当前 kernel syscall 已实化为真实 provider 闭环。`context` 和 `memory` 默认使用 SQLite，`storage` 使用安全本地文件系统和 SQLite FTS 索引，`tool` 只注册真实 builtin/manifest tool，`llm` 必须配置真实 OpenAI-compatible/LiteLLM/HF/local provider。缺少真实 runtime、ROS2、人机或 LLM backend 时，syscall 必须返回稳定错误码并出现在 status/audit 中，不允许产品代码伪造成功。完整 syscall、权限、错误码和验证命令见 `docs/kernel_syscalls.md`。

模板目录：

```text
/home/ubuntu/Agentic_OS_ROS_publish/agentic_apps/app_template
```

Agentic App 不是 ROS2 package。Agentic App 是运行在 AgenticOS / Agentic Runtime 上的用户态应用。

---

## 1. 一句话模型

开发者写 Agentic App 时，写的是：

```text
当 Runtime 已经把一个任务分配给本 app 后，本 app 如何理解任务、规划步骤、校验风险、调用 AgenticOS 系统调用、保存结果、向用户汇报。
```

开发者不写：

```text
全局 app 路由、ROS2 node、ROS2 topic/service/action、Nav2/MoveIt 直接调用、机器人实时闭环控制、硬件驱动。
```

正确层级：

```text
User
  -> AgenticOS global dispatcher
  -> Agentic App
  -> Agentic SDK / system calls
  -> Agentic Runtime / Kernel
  -> permission, lock, safety, audit
  -> robot capability bridge
  -> ROS2
  -> robot hardware
```

Agentic App 永远站在 `Agentic SDK / system calls` 这一层之上。

---

## 2. 开发者必须遵守的边界

Agentic App 代码中禁止出现：

```text
import rclpy
ros2 topic pub
ros2 topic echo
ros2 service call
ros2 action send_goal
/cmd_vel
/scan
/odom
/tf
/navigate_to_pose
MoveIt action
Nav2 action
```

也禁止绕过 Runtime：

```text
App -> ROS2
App -> vendor driver
App -> /opt/agentic internal file overwrite
App -> shell command 控制机器人
```

如果 app 需要机器人移动、观察、拍照、机械臂、夹爪、记忆、存储、LLM 或工具调用，只能通过 `ctx.*` 系统调用。

---

## 3. App 生命周期

一次 app 运行的基本流程是：

```text
1. 用户发出自然语言任务。
2. AgenticOS global dispatcher 选择合适的 app。
3. Runtime 创建 session、context、audit correlation。
4. Runtime 调用 app 的 entrypoint: main:run。
5. app 在 run(ctx, **kwargs) 中执行：
   - 读取任务和上下文
   - 调用 app-level planner 生成结构化 plan
   - 用 rules 校验 plan
   - 调用 ctx.* 系统调用执行步骤
   - 写 memory、storage、report
   - 返回结构化 result
6. Runtime 记录 session、syscall、audit、artifact。
```

开发者只实现第 5 步。

---

## 4. 从模板创建 App

进入 app workspace：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_apps
cp -r app_template my_agentic_app
```

不要把 Agentic App 放到：

```text
/home/ubuntu/ros2_ws/src
```

`/home/ubuntu/ros2_ws/src` 是 ROS2 应用包区域，不是 Agentic App workspace。

新 app 推荐结构：

```text
my_agentic_app/
  README.md
  app.yaml
  main.py
  prompts/
    system.md
  workflows/
    default.yaml
  context/
    app_context.schema.json
    default_context.yaml
  memory/
    memory_keys.yaml
  rules/
    plan.schema.json
    result.schema.json
    validation.py
  skills/
    used_skills.yaml
  tools/
    planner.py
    context_builder.py
    result_builder.py
  storage/
    .gitkeep
  tests/
    test_manifest.py
    test_plan_validation.py
    test_main_flow.py
    test_no_direct_ros_access.py
```

说明：

- `README.md`、`app.yaml`、`main.py`、`prompts/system.md`、`workflows/default.yaml` 是每个 app 都要维护的核心文件。
- `context/`、`memory/`、`rules/`、`skills/`、`tools/`、`tests/` 是开发者根据 app 需要新增内容的目录。
- `storage/` 保留 `.gitkeep`。运行时产物优先通过 `ctx.kernel.storage.*` 写入 Runtime 管理的安全存储，不要在产品代码里直接写 `/opt/agentic`。

---

## 5. 开发者文件职责

| 位置 | 开发者写什么 | 作用 |
| --- | --- | --- |
| `README.md` | app 说明、能力、权限、demo、安全限制 | 让别人知道 app 怎么用 |
| `app.yaml` | app 身份、入口、权限、能力、安全策略、运行限制 | Runtime 装载和授权依据 |
| `main.py` | `async def run(ctx, **kwargs)` | app 执行入口 |
| `prompts/system.md` | app-level planner system prompt | 约束 LLM 只输出结构化 plan |
| `workflows/default.yaml` | 默认工作流 | 描述 plan、validate、execute、report 的顺序 |
| `context/` | app-local context schema 和默认值 | 说明一次任务中 app 自己维护哪些字段 |
| `memory/` | 允许读写的 memory key 和语义 | 防止随意写长期记忆 |
| `rules/` | JSON Schema 和确定性校验 | 校验 LLM plan，拒绝危险或无效计划 |
| `skills/` | 本 app 使用或提供的 skill 合同 | 声明输入、输出、权限、资源、审计 |
| `tools/` | 纯 Python helper | planner、context builder、result builder 等 |
| `storage/` | app 包内静态占位或示例 | 不直接承载 Runtime evidence |
| `tests/` | 单元测试和边界测试 | 证明 app 按合同运行 |

---

## 6. `app.yaml` 怎么写

`app.yaml` 是 Runtime 认识 app 的 manifest。最小模板：

```yaml
name: my_agentic_app
version: 0.1.0
description: Inspect a named place and report structured findings.
entrypoint: main:run

permissions:
  - report.say
  - human.ask
  - world.read
  - robot.state.read
  - robot.move
  - perception.inspect
  - memory.read
  - memory.write
  - storage.read

required_capabilities:
  - report.say
  - human.ask
  - world.resolve_place
  - robot.get_state
  - robot.navigate_to
  - robot.inspect_area
  - memory.recall
  - memory.remember

safety_policy:
  allow_autonomous_navigation: false
  allow_manipulation: false
  require_human_confirmation_for:
    - robot.navigate_to
  forbidden_zones: []
  max_task_duration_s: 180

runtime_limits:
  max_concurrent_tasks: 1
  max_retries_per_skill: 0
  max_memory_write_per_task: 3
  llm_planning_enabled: true
```

原则：

- `permissions` 只申请 app 真正需要的权限。
- `required_capabilities` 只列 app 执行路径会用到的系统调用能力。
- 涉及导航、机械臂、夹爪的 app，必须在 `safety_policy` 中写清楚是否需要人类确认。
- `allow_autonomous_navigation` 和 `allow_manipulation` 不是用来绕过安全系统的开关。即使设为 true，动作仍然必须经过 Runtime permission、resource lock、safety guard 和 audit。
- `app.yaml` 不能授权 app 直接访问 ROS2。

常用权限：

| 权限 | 何时需要 |
| --- | --- |
| `report.say` | 向用户汇报 |
| `human.ask` | 询问用户或请求确认 |
| `world.read` | 解析地点、读取世界模型 |
| `robot.state.read` | 读取机器人状态 |
| `robot.move` | 导航 |
| `robot.stop` | 停止机器人 |
| `perception.inspect` | 检查区域 |
| `perception.observe` | 观察目标 |
| `perception.capture` | 拍照并记录证据 |
| `arm.state.read` | 读取机械臂状态 |
| `arm.move.named` | 执行已批准的机械臂命名动作 |
| `gripper.control` | 控制夹爪 |
| `memory.read` | 读取 app 记忆 |
| `memory.write` | 写入 app 记忆 |
| `storage.read` | 读取 Runtime 管理的 artifact 或 evidence index |

---

## 7. 系统调用接口

开发者应该把 `ctx` 理解为 AgenticOS 给 app 的系统调用表。不要自己实现这些能力，也不要在产品代码里写本地替代路径。

### 7.1 Context 和 App 信息

```python
ctx.session_id
ctx.app_manifest
```

用途：

- `ctx.session_id` 是本次运行的 session id。写 artifact、plan id、result id 时都应该带上它。
- `ctx.app_manifest` 是当前 app 的 manifest 对象。不要在运行时修改它。

### 7.2 Robot

```python
state = await ctx.robot.get_state()
nav = await ctx.robot.navigate_to(place, timeout_s=120)
inspection = await ctx.robot.inspect_area(place, timeout_s=60)
stop = await ctx.robot.stop(reason="app_requested")
```

规则：

- 所有移动必须走 `ctx.robot.navigate_to(...)`。
- 所有停止必须走 `ctx.robot.stop(...)`。
- `navigate_to` 的参数必须来自 `ctx.world.resolve_place(...)` 或已校验 plan，不要直接使用未校验的用户文本。
- 不要发布速度，不要控制实时闭环。

### 7.3 World

```python
place = await ctx.world.resolve_place(name)
```

规则：

- 用户说的“厨房”“门口”“桌子旁”这类自然语言地点，必须先解析为 Runtime 注册地点。
- 如果地点不存在、不允许进入或需要确认，app 应调用 `ctx.human.ask(...)` 或返回结构化错误。

### 7.4 Perception

```python
observation = await ctx.perception.observe(target="workspace", timeout_s=10)
photo = await ctx.perception.capture_photo(target="workspace", label="before_grasp", timeout_s=5)
```

规则：

- 观察和拍照都走 Runtime 管理的 camera bridge。
- 证据路径和 metadata 由 Runtime 管理，app 只保存引用，不复制 raw sensor stream。
- 不要直接订阅 camera、scan、point cloud 或 tf。

### 7.5 Arm 和 Gripper

```python
arm_state = await ctx.arm.get_state()
move = await ctx.arm.move_named("arm_home", timeout_s=8)

opened = await ctx.gripper.open(timeout_s=5)
closed = await ctx.gripper.close(force="low", timeout_s=5)
custom = await ctx.gripper.set("close_gripper_low_force", force="low", timeout_s=5)
```

规则：

- App 只能调用 allowlisted named arm action。
- App 不写 joint trajectory，不调用 MoveIt，不发 servo command。
- 抓取类 app 必须在 rules 中校验目标、风险、确认状态和资源锁需求。

### 7.6 Human

```python
answer = await ctx.human.ask(
    "是否允许机器人前往厨房？",
    options=["yes", "no"],
    timeout_s=60,
    require_confirmation=True,
)
```

规则：

- 不确定、危险、超出权限、地点不明确时，问人。
- `human.ask` 的结果也要进入 result 和 audit 语义，不要只打印。

### 7.7 Report

```python
await ctx.report.say("任务开始。")
await ctx.report.log("validated plan", level="info")
```

规则：

- 用户可见信息用 `ctx.report.say(...)`。
- 调试信息可以用 `ctx.report.log(...)`，但不要把大量 sensor raw data 写入 report。

### 7.8 App Memory

```python
last = await ctx.memory.recall("last_inspection")
await ctx.memory.remember("last_inspection", result)
```

`ctx.memory` 用于 app 级长期记忆，适合保存：

- 用户偏好。
- 上一次任务结果摘要。
- 已确认的配置。
- 小型结构化状态。

不要用 `ctx.memory` 保存：

- 大文件。
- 图片。
- ROS2 raw log。
- 高频传感器数据。
- 未经用户确认的敏感信息。

### 7.9 Kernel Memory

```python
await ctx.kernel.memory.add(
    "厨房检查完成，未发现异常。",
    key=f"{ctx.session_id}:kitchen_summary",
    memory_type="episodic",
    category="inspection",
    tags=["inspection", "kitchen"],
    context="room_inspection",
)

matches = await ctx.kernel.memory.search(
    "厨房 最近异常",
    limit=5,
    category="inspection",
)
```

`ctx.kernel.memory` 用于更底层的语义记忆和检索型记忆。开发者使用它时要提供 metadata，让 Runtime 能做隔离、检索、压缩、保留策略和审计。

推荐 metadata：

| 字段 | 含义 |
| --- | --- |
| `memory_type` | `episodic`、`semantic`、`preference`、`procedure` |
| `category` | `inspection`、`navigation`、`grasping`、`user_preference` |
| `tags` | 检索标签 |
| `context` | 本 app 的任务上下文 |
| `sharing_policy` | `private`、`shared`、`operator_shared` |
| `robot` | `place_id`、`frame_id`、`sensor_refs` 等机器人相关元数据 |

选择规则：

- 只想按 key 保存 app 状态，用 `ctx.memory`。
- 想让 Runtime 做语义检索、跨步骤上下文注入、压缩或长期知识管理，用 `ctx.kernel.memory`。

### 7.10 Kernel Storage

```python
await ctx.kernel.storage.write(
    f"runs/{ctx.session_id}/plan.json",
    validated_plan,
    artifact_type="plan",
)

retrieved = await ctx.kernel.storage.retrieve(
    "kitchen inspection",
    collection_name=f"runs/{ctx.session_id}",
    limit=5,
)
```

`ctx.kernel.storage` 用于 Runtime 管理的安全 artifact。适合保存：

- validated plan。
- step results。
- final result。
- 小型 JSON 报告。
- 可追溯 evidence 引用。

不要用它保存：

- 机器人实时控制命令。
- 未压缩的大型 sensor stream。
- `/opt/agentic` 配置覆盖。
- ROS2 workspace 文件。

命名建议：

```text
runs/<session_id>/plan.json
runs/<session_id>/steps.jsonl
runs/<session_id>/result.json
runs/<session_id>/evidence_refs.json
```

### 7.11 Storage Convenience API

```python
photos = await ctx.storage.list_recent_photos(limit=5)
```

这个接口用于读取 Runtime 管理的照片证据索引。app 可以引用照片 evidence，不要复制或改写 Runtime raw evidence。

### 7.12 Kernel LLM

```python
response = await ctx.kernel.llm.chat(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task_payload},
    ],
    response_format={"type": "json_object"},
    timeout_s=30,
)
```

规则：

- LLM 只负责生成候选 plan 或结构化解释。
- LLM 输出必须通过 `rules/` 校验后才能执行。
- 不要让 LLM 输出 ROS2 命令、Python 代码或 shell 命令。

### 7.13 Kernel Tool

```python
tool_result = await ctx.kernel.tool.call("tool.name", {"arg": "value"}, timeout_s=10)
```

规则：

- 工具调用必须是 Runtime 注册工具。
- 工具输出仍要经过 app 的规则校验后才能影响机器人动作。

### 7.14 Generic Skill Call

```python
result = await ctx.call_skill("capability.name", {"arg": "value"})
```

只有在能力已经由 Runtime 注册、权限已经在 `app.yaml` 声明、输入输出 schema 已经明确时，才使用 `ctx.call_skill(...)`。优先使用更明确的 typed SDK，例如 `ctx.robot.navigate_to(...)`、`ctx.perception.observe(...)`。

---

## 8. Context 应该怎么设计

AgenticOS 有两类 context：

| 类型 | 谁管理 | 开发者做什么 |
| --- | --- | --- |
| Runtime context | Runtime / Kernel | 通过 `ctx.session_id`、`ctx.app_manifest` 和系统调用读取 |
| App-local context | 当前 app | 在 `context/` 中定义 schema，在运行时构造普通 dict |

开发者不实现 Runtime session manager，也不直接改 Runtime context 文件。开发者只定义 app-local context。

示例 `context/app_context.schema.json`：

```json
{
  "type": "object",
  "required": ["session_id", "task_id", "dry_run", "operator_confirmed"],
  "properties": {
    "session_id": {"type": "string"},
    "task_id": {"type": "string"},
    "dry_run": {"type": "boolean"},
    "operator_confirmed": {"type": "boolean"},
    "target_place": {"type": "string"},
    "plan_id": {"type": "string"},
    "evidence_refs": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

示例 `tools/context_builder.py`：

```python
from uuid import uuid4


def build_run_context(ctx, task: dict) -> dict:
    return {
        "session_id": ctx.session_id,
        "task_id": str(task.get("task_id") or f"task_{uuid4().hex[:12]}"),
        "dry_run": bool(task.get("dry_run", True)),
        "operator_confirmed": bool(task.get("operator_confirmed", False)),
        "target_place": str(task.get("place", "")),
        "plan_id": f"plan_{uuid4().hex[:12]}",
        "evidence_refs": [],
    }
```

Context 使用原则：

- 每次运行都构造新的 app-local context。
- 不把大文件放进 context。
- 不把 context 当长期记忆。
- 需要长期保留的摘要写 `ctx.memory` 或 `ctx.kernel.memory`。
- 需要 artifact 的内容写 `ctx.kernel.storage`。

---

## 9. Memory 应该怎么设计

在 `memory/memory_keys.yaml` 里声明本 app 允许读写哪些 key。

示例：

```yaml
keys:
  last_inspection:
    api: ctx.memory
    scope: app
    value_type: object
    write_when: task_finished
    retention: latest_only

  user_place_preference:
    api: ctx.memory
    scope: user
    value_type: object
    write_when: user_confirmed
    retention: until_user_deletes

  inspection_episode:
    api: ctx.kernel.memory
    scope: app
    memory_type: episodic
    category: inspection
    write_when: task_finished
    searchable: true
```

开发规则：

- 先声明，再读写。
- 写入前压缩成摘要，不写 raw data。
- 对用户偏好类 memory，必须来自用户确认。
- 对机器人证据类 memory，只保存 evidence reference 和摘要。
- 每个任务写入数量要受 `runtime_limits.max_memory_write_per_task` 限制。

示例：

```python
last = await ctx.memory.recall("last_inspection")

await ctx.memory.remember(
    "last_inspection",
    {
        "place": "kitchen",
        "summary": "未发现异常",
        "session_id": ctx.session_id,
    },
)

await ctx.kernel.memory.add(
    "厨房检查完成，未发现异常。",
    key=f"{ctx.session_id}:inspection_episode",
    memory_type="episodic",
    category="inspection",
    tags=["kitchen", "inspection"],
)
```

---

## 10. Storage 应该怎么设计

运行时产物优先写 Runtime 管理的 storage：

```python
await ctx.kernel.storage.write(f"runs/{ctx.session_id}/plan.json", plan)
await ctx.kernel.storage.write(f"runs/{ctx.session_id}/result.json", result)
```

`storage/` 目录在 app 包中主要放：

- `.gitkeep`
- 静态样例。
- schema 示例。
- 本地开发说明。

不要在产品代码里直接拼绝对路径写文件。不要写 `/opt/agentic/var/evidence`，不要覆盖 Runtime 配置。

推荐 artifact：

| 文件 | 内容 |
| --- | --- |
| `runs/<session_id>/plan.json` | 通过规则校验的 plan |
| `runs/<session_id>/steps.jsonl` | 每一步系统调用摘要 |
| `runs/<session_id>/result.json` | app final result |
| `runs/<session_id>/evidence_refs.json` | Runtime evidence 引用 |

---

## 11. Planner 应该怎么写

AgenticOS 有两层 LLM：

| 层 | 谁负责 | 输入 | 输出 |
| --- | --- | --- | --- |
| Global dispatcher | Runtime / 平台 | 用户原始请求、app metadata | 选择 app，生成分配任务 |
| App-level planner | 当前 app | Runtime 分配给本 app 的 task、context、memory 摘要 | 本 app 可执行 plan |

开发者只写 app-level planner。

禁止在 app 中直接解析用户原始输入：

```python
if "蓝色" in user_text:
    color = "blue"
```

允许根据已校验 plan 执行分支：

```python
if step["type"] == "inspect_area":
    ...
```

因为 `step` 已经来自 LLM planner 的结构化输出，并通过 `rules/` 校验。

示例 `prompts/system.md`：

```text
You are the app-level planner for room_inspection_app.

Return only JSON.
Do not return Python code, shell commands, ROS2 topics, ROS2 services, ROS2 actions, or navigation internals.

Allowed step types:
- resolve_place
- get_robot_state
- ask_human_confirmation
- navigate_to
- inspect_area
- remember_result
- report

If the target place is missing or ambiguous, return:
{"status": "needs_clarification", "question": "..."}

If the task is outside this app's capability, return:
{"status": "rejected", "error_code": "OUT_OF_SCOPE", "reason": "..."}

Otherwise return:
{
  "status": "ready",
  "risk_level": "low|medium|high",
  "requires_human_confirmation": true|false,
  "steps": [...]
}
```

示例 `tools/planner.py`：

```python
import json
from pathlib import Path


def _system_prompt() -> str:
    return (Path(__file__).parents[1] / "prompts" / "system.md").read_text(encoding="utf-8")


async def make_plan(ctx, task: dict, run_context: dict, memory_summary: dict | None = None) -> dict:
    payload = {
        "task": task,
        "context": run_context,
        "memory_summary": memory_summary or {},
    }
    response = await ctx.kernel.llm.chat(
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        timeout_s=30,
    )
    if not response.success:
        return {
            "status": "rejected",
            "error_code": response.error_code or "LLM_PLANNER_FAILED",
            "reason": "planner system call failed",
        }
    if isinstance(response.response, dict):
        return response.response
    return json.loads(str(response.response))
```

---

## 12. Rules 应该怎么写

LLM 输出不能直接执行。必须先进 `rules/`。

示例 `rules/plan.schema.json`：

```json
{
  "type": "object",
  "required": ["status"],
  "properties": {
    "status": {
      "type": "string",
      "enum": ["ready", "needs_clarification", "rejected"]
    },
    "risk_level": {
      "type": "string",
      "enum": ["low", "medium", "high"]
    },
    "requires_human_confirmation": {"type": "boolean"},
    "question": {"type": "string"},
    "error_code": {"type": "string"},
    "reason": {"type": "string"},
    "steps": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type"],
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "resolve_place",
              "get_robot_state",
              "ask_human_confirmation",
              "navigate_to",
              "inspect_area",
              "remember_result",
              "report"
            ]
          },
          "place": {"type": "string"},
          "message": {"type": "string"}
        }
      }
    }
  }
}
```

示例 `rules/validation.py`：

```python
ALLOWED_STEPS = {
    "resolve_place",
    "get_robot_state",
    "ask_human_confirmation",
    "navigate_to",
    "inspect_area",
    "remember_result",
    "report",
}


class PlanRejected(ValueError):
    def __init__(self, error_code: str, reason: str) -> None:
        super().__init__(reason)
        self.error_code = error_code
        self.reason = reason


def validate_plan(plan: dict, app_manifest, run_context: dict) -> dict:
    if not isinstance(plan, dict):
        raise PlanRejected("PLAN_NOT_OBJECT", "plan must be a JSON object")

    status = plan.get("status")
    if status not in {"ready", "needs_clarification", "rejected"}:
        raise PlanRejected("PLAN_BAD_STATUS", "invalid plan status")

    if status != "ready":
        return plan

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise PlanRejected("PLAN_EMPTY_STEPS", "ready plan must contain steps")

    for step in steps:
        step_type = step.get("type")
        if step_type not in ALLOWED_STEPS:
            raise PlanRejected("PLAN_STEP_NOT_ALLOWED", f"step not allowed: {step_type}")

    if plan.get("risk_level") in {"medium", "high"}:
        plan["requires_human_confirmation"] = True

    if plan.get("requires_human_confirmation") and not run_context.get("operator_confirmed"):
        plan["needs_runtime_confirmation"] = True

    return plan
```

Rules 的职责：

- 校验 schema。
- 校验 step 白名单。
- 校验参数范围。
- 校验是否需要人类确认。
- 校验是否符合 `app.yaml` 的安全策略。
- 生成结构化拒绝原因。

Rules 不能做：

- 调 ROS2。
- 根据用户原始文本猜 intent。
- 绕过 Runtime 权限。

---

## 13. `main.py` 推荐骨架

下面是一个完整的 app 入口骨架。它面向正式系统调用，不写本地 mock 路径。

```python
from agentic_runtime.sdk import AgentContext

from rules.validation import PlanRejected, validate_plan
from tools.context_builder import build_run_context
from tools.planner import make_plan


async def run(ctx: AgentContext, **kwargs):
    task = dict(kwargs.get("task") or kwargs)
    run_context = build_run_context(ctx, task)

    await ctx.report.say("任务已接收，正在规划。")

    previous = await ctx.memory.recall("last_inspection", default={})
    plan = await make_plan(ctx, task, run_context, memory_summary={"last_inspection": previous})

    try:
        plan = validate_plan(plan, ctx.app_manifest, run_context)
    except PlanRejected as exc:
        result = {
            "success": False,
            "error_code": exc.error_code,
            "reason": exc.reason,
            "session_id": ctx.session_id,
        }
        await ctx.report.say(f"计划被拒绝：{exc.reason}")
        await ctx.kernel.storage.write(f"runs/{ctx.session_id}/result.json", result)
        return result

    if plan["status"] == "needs_clarification":
        answer = await ctx.human.ask(plan["question"], timeout_s=60)
        result = {
            "success": False,
            "error_code": "NEEDS_CLARIFICATION",
            "answer": answer.to_dict(),
            "session_id": ctx.session_id,
        }
        await ctx.kernel.storage.write(f"runs/{ctx.session_id}/result.json", result)
        return result

    if plan["status"] == "rejected":
        result = {
            "success": False,
            "error_code": plan.get("error_code", "PLAN_REJECTED"),
            "reason": plan.get("reason", ""),
            "session_id": ctx.session_id,
        }
        await ctx.kernel.storage.write(f"runs/{ctx.session_id}/result.json", result)
        return result

    if plan.get("needs_runtime_confirmation"):
        answer = await ctx.human.ask(
            "该任务需要机器人动作，是否继续？",
            options=["yes", "no"],
            timeout_s=60,
            require_confirmation=True,
        )
        if answer.answer != "yes":
            result = {
                "success": False,
                "error_code": "USER_DECLINED",
                "session_id": ctx.session_id,
            }
            await ctx.report.say("用户取消任务。")
            await ctx.kernel.storage.write(f"runs/{ctx.session_id}/result.json", result)
            return result

    await ctx.kernel.storage.write(f"runs/{ctx.session_id}/plan.json", plan)

    step_results = []
    resolved_places = {}
    latest_inspection = None

    for step in plan["steps"]:
        step_type = step["type"]

        if step_type == "resolve_place":
            place_name = step["place"]
            place = await ctx.world.resolve_place(place_name)
            resolved_places[place_name] = place.to_dict()
            step_results.append({"type": step_type, "success": True, "place": place.to_dict()})

        elif step_type == "get_robot_state":
            state = await ctx.robot.get_state()
            step_results.append({"type": step_type, "success": True, "state": state.to_dict()})

        elif step_type == "ask_human_confirmation":
            answer = await ctx.human.ask(
                step.get("message", "是否继续？"),
                options=["yes", "no"],
                timeout_s=60,
                require_confirmation=True,
            )
            if answer.answer != "yes":
                await ctx.robot.stop(reason="user_declined")
                result = {
                    "success": False,
                    "error_code": "USER_DECLINED",
                    "steps": step_results,
                    "session_id": ctx.session_id,
                }
                await ctx.kernel.storage.write(f"runs/{ctx.session_id}/result.json", result)
                return result
            step_results.append({"type": step_type, "success": True, "answer": answer.to_dict()})

        elif step_type == "navigate_to":
            nav = await ctx.robot.navigate_to(step["place"], timeout_s=int(step.get("timeout_s", 120)))
            step_results.append({"type": step_type, "success": True, "audit_id": nav.audit_id})

        elif step_type == "inspect_area":
            latest_inspection = await ctx.robot.inspect_area(step["place"], timeout_s=int(step.get("timeout_s", 60)))
            step_results.append({"type": step_type, "success": True, "inspection": latest_inspection.to_dict()})

        elif step_type == "remember_result":
            if latest_inspection is not None:
                await ctx.memory.remember("last_inspection", latest_inspection.to_dict())
                await ctx.kernel.memory.add(
                    latest_inspection.summary,
                    key=f"{ctx.session_id}:inspection",
                    memory_type="episodic",
                    category="inspection",
                    tags=["inspection"],
                )
            step_results.append({"type": step_type, "success": True})

        elif step_type == "report":
            await ctx.report.say(step["message"])
            step_results.append({"type": step_type, "success": True})

    result = {
        "success": True,
        "session_id": ctx.session_id,
        "steps": step_results,
        "places": resolved_places,
    }
    await ctx.kernel.storage.write(f"runs/{ctx.session_id}/steps.json", step_results)
    await ctx.kernel.storage.write(f"runs/{ctx.session_id}/result.json", result)
    await ctx.report.say("任务完成。")
    return result
```

生产 app 可以拆分更多 helper，但执行原则不变：plan 必须校验，动作必须走系统调用，结果必须结构化返回。

---

## 14. Workflows 怎么写

`workflows/default.yaml` 描述 app 的默认流程，不是 ROS2 launch 文件。

简单 app：

```yaml
name: default
version: 0.1.0
steps:
  - id: build_context
    uses: tools.context_builder.build_run_context
  - id: plan
    uses: tools.planner.make_plan
  - id: validate
    uses: rules.validation.validate_plan
  - id: execute
    uses: main.run
  - id: persist
    uses: ctx.kernel.storage.write
  - id: report
    uses: ctx.report.say
```

原则：

- workflow 只描述 app 内部流程。
- workflow 不能出现 ROS2 topic/service/action。
- workflow 中出现的每个 helper 都要能在代码中找到。

---

## 15. Skills 怎么声明

大多数 app 直接使用系统已有 typed SDK 就够了。需要声明 app 使用的能力时，可以在 `skills/used_skills.yaml` 中写：

```yaml
used_skills:
  - name: world.resolve_place
    reason: Resolve user-facing place names before navigation.
  - name: robot.navigate_to
    reason: Move through Runtime permission, lock, safety and audit.
  - name: robot.inspect_area
    reason: Inspect a registered place through perception bridge.
  - name: memory.remember
    reason: Store final task summary.
  - name: report.say
    reason: Report task progress and result to the user.
```

如果 app 定义自己的高层 skill manifest，manifest 只描述合同，不实现 ROS2 后端：

```yaml
name: my_app.inspect_then_report
version: 0.1.0
description: Inspect a place and report findings.
input_schema:
  type: object
  required: [place]
  properties:
    place:
      type: string
output_schema:
  type: object
  required: [success]
  properties:
    success:
      type: boolean
permission_requirements:
  - world.read
  - perception.inspect
resource_requirements:
  locks:
    - camera
safety_constraints:
  require_known_place: true
  allow_cancel: true
timeout_s: 60
retry_policy:
  max_attempts: 0
  retry_on: []
backend:
  type: runtime_skill
observability:
  audit: true
  record_result: true
```

---

## 16. 错误处理

所有失败都返回结构化 result，不返回随意字符串。

推荐格式：

```python
{
    "success": False,
    "error_code": "PLACE_NOT_FOUND",
    "reason": "目标地点不存在或未注册",
    "recoverable": True,
    "suggested_recovery": ["ask_user_for_known_place"],
    "session_id": ctx.session_id,
}
```

常见错误码：

| 错误码 | 含义 |
| --- | --- |
| `OUT_OF_SCOPE` | 用户任务不属于本 app |
| `NEEDS_CLARIFICATION` | 需要用户补充信息 |
| `PLAN_BAD_STATUS` | planner 输出非法 |
| `PLAN_STEP_NOT_ALLOWED` | step 不在白名单 |
| `USER_DECLINED` | 用户拒绝继续 |
| `PLACE_NOT_FOUND` | 地点无法解析 |
| `PERMISSION_DENIED` | 权限不足 |
| `RESOURCE_LOCKED` | 资源被占用 |
| `SAFETY_REJECTED` | 安全系统拒绝 |
| `SKILL_TIMEOUT` | 系统调用超时 |
| `BACKEND_UNAVAILABLE` | Runtime 后端不可用 |
| `UNEXPECTED_ERROR` | 未分类错误 |

危险动作失败时，app 应优先调用：

```python
await ctx.robot.stop(reason="task_failed")
```

然后写 result、storage 和 report。

---

## 17. 测试怎么写

测试目标不是替代系统调用，而是证明 app 会正确调用系统调用。

推荐测试：

| 测试 | 目的 |
| --- | --- |
| `test_manifest.py` | `app.yaml` 字段完整，权限最小 |
| `test_plan_validation.py` | rules 能接受合法 plan，拒绝非法 plan |
| `test_main_flow.py` | `run(ctx, **kwargs)` 按顺序调用 `ctx.*` |
| `test_no_direct_ros_access.py` | 静态扫描没有 ROS2 直接访问 |
| `test_error_paths.py` | planner 拒绝、用户取消、系统调用失败时返回结构化错误 |

`tests/` 中可以定义 Fake Context：

```python
class FakeReport:
    def __init__(self):
        self.messages = []

    async def say(self, message):
        self.messages.append(message)
        return {"success": True}
```

规则：

- Fake Context 只能放在 `tests/`。
- 产品代码不能根据“真实接口不存在”切换到 fake。
- 测试要验证 app 调用了 `ctx.robot.navigate_to`，而不是验证 ROS2 行为。

静态边界测试示例：

```python
from pathlib import Path


FORBIDDEN = [
    "import rclpy",
    "ros2 topic",
    "ros2 service",
    "ros2 action",
    "/cmd_vel",
    "/scan",
    "/odom",
    "/tf",
    "/navigate_to_pose",
]


def test_no_direct_ros_access():
    root = Path(__file__).parents[1]
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{token} found in {path}"
```

---

## 18. 本科生开发顺序

按这个顺序做，不容易乱：

1. 用一句话写清楚 app 要做什么。
2. 写出 app 不做什么。
3. 列出需要的系统调用。
4. 复制 `app_template`。
5. 修改 `app.yaml` 的 name、description、permissions、required_capabilities、safety_policy。
6. 写 `README.md`。
7. 写 `context/app_context.schema.json`。
8. 写 `memory/memory_keys.yaml`。
9. 写 `prompts/system.md`，要求 LLM 只输出 JSON plan。
10. 写 `rules/plan.schema.json` 和 `rules/validation.py`。
11. 写 `tools/context_builder.py`。
12. 写 `tools/planner.py`。
13. 写 `main.py`，只调用 `ctx.*`。
14. 写测试。
15. 运行测试和静态扫描。
16. 写 demo 命令。
17. 检查 README、manifest、权限、安全策略是否一致。

---

## 19. README 应该包含什么

每个 app 的 `README.md` 至少包含：

```markdown
# my_agentic_app

## Purpose
这个 app 做什么。

## User Tasks
- 用户可以怎么说。

## Capabilities
- 使用哪些 AgenticOS 系统调用。

## Permissions
- 需要哪些权限，为什么。

## Safety
- 哪些动作需要人类确认。
- 哪些事情 app 永远不做。

## Memory
- 读取哪些 key。
- 写入哪些 key。

## Storage
- 写入哪些 artifact。

## Demo
运行 demo 的命令。

## Tests
运行测试的命令。
```

---

## 20. Demo 命令

文档中必须给出 demo 命令。示例：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m agentic_runtime.cli run-app my_agentic_app --place 厨房 --mock
```

真实机器人 demo 也必须仍然走 Runtime：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
AGENTIC_RUNTIME_CONFIG=/opt/agentic/etc/agentic_robot.yaml \
python -m agentic_runtime.cli run-app my_agentic_app --place 厨房 --no-mock
```

不要在 README 里指导用户运行 ROS2 topic/service/action 来替代 app。

---

## 21. Codex 任务模板

可以把下面这段给 Codex，用来创建新 app：

```text
请基于 /home/ubuntu/Agentic_OS_ROS_publish/agentic_apps/app_template
创建一个新的 Agentic App：<app_id>。

目标：
<用一句话说明 app 做什么>

要求：
1. 产品代码只能调用 AgenticOS SDK / system calls，也就是 ctx.*。
2. 不允许 import rclpy。
3. 不允许直接调用 ROS2 topic/service/action/CLI。
4. 不允许发布 /cmd_vel。
5. 不允许订阅 /scan、/odom、/tf。
6. 不允许直接调用 Nav2 或 MoveIt。
7. 不要因为接口在本地暂时不可用就删掉接口调用或写产品 mock。
8. App 只实现被 Runtime 选中后的 app-level planner，不实现 global dispatcher。
9. 用户原始输入只能交给 LLM planner，不能用关键词、字段、正则或 if/elif 解析。
10. LLM planner 只能输出结构化 JSON plan。
11. 所有 plan 必须经过 rules/ 校验后才能执行。
12. 必须写 app.yaml、main.py、prompts/system.md、workflows/default.yaml。
13. 必须定义 context、memory、rules、storage 的开发合同。
14. 必须写测试，包括 no direct ROS access 静态扫描。
15. 最后列出改动文件、运行命令、测试结果、剩余风险和下一步。
```

---

## 22. 完成定义

一个 Agentic App 完成时，至少满足：

- 从 `app_template` 派生。
- `README.md` 写清楚用途、权限、安全、demo。
- `app.yaml` 字段完整，权限最小化。
- `main.py` 入口是 `async def run(ctx: AgentContext, **kwargs)`。
- 产品代码只调用 `ctx.*` 系统调用。
- 没有任何直接 ROS2 访问。
- 用户原始输入只进入 LLM planner。
- planner 输出 JSON plan。
- `rules/` 对 plan 做确定性校验。
- 危险动作需要 human confirmation。
- navigation、arm、gripper 等动作都经过 Runtime 系统调用。
- memory key 已声明，写入受限。
- storage artifact 路径按 `runs/<session_id>/...` 命名。
- 失败返回结构化错误码。
- 测试通过。
- demo 命令已写入 README。

---

## 23. 最重要的检查表

提交前逐项检查：

```text
[ ] App 没有 import rclpy。
[ ] App 没有 ROS2 topic/service/action/CLI 字符串。
[ ] App 没有 /cmd_vel、/scan、/odom、/tf。
[ ] App 没有直接调用 Nav2 或 MoveIt。
[ ] App 使用 ctx.robot / ctx.perception / ctx.arm / ctx.gripper 等系统调用。
[ ] App 使用 ctx.memory 或 ctx.kernel.memory 管理记忆。
[ ] App 使用 ctx.kernel.storage 管理运行 artifact。
[ ] LLM 输出先经过 rules 校验。
[ ] 高风险动作先经过 ctx.human.ask。
[ ] result 包含 success、error_code、reason、session_id。
[ ] README 有 demo。
[ ] tests 有 no direct ROS access。
```
