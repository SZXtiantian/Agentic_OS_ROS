# 彩色方块抓取 Agentic App 技术方案

最后更新：2026-06-22

本文是基于当前真实模板：

```text
/home/ubuntu/Agentic_OS_ROS_publish/agentic_apps/app_template
```

为 `color_block_grasper_agent` 编写的技术方案。它可以交给 Codex `goal` 执行。

本文讨论的是 Agentic App，不是 ROS2 app。现有 ROS2 抓取能力可以继续存在于：

```text
/home/ubuntu/ros2_ws/src/color_block_grasper
```

但 Agentic App 不在 `ros2_ws` 中开发，也不能直接调用 ROS2。

---

## 1. 目标

从模板复制出一个新 app：

```text
/home/ubuntu/Agentic_OS_ROS_publish/agentic_apps/color_block_grasper_agent
```

它支持：

- 抓取红色方块。
- 抓取蓝色方块。
- 抓取绿色方块。
- 放下当前方块。
- 默认 dry-run。
- 只有明确授权后才允许真实机械臂动作。

用户示例：

```bash
/opt/agentic/bin/agentic --json "夹取蓝色方块"
```

真实动作示例：

```bash
AGENTIC_COLOR_BLOCK_GRASPER_ALLOW_MOTION=1 \
  /opt/agentic/bin/agentic --real --yes --json "夹取蓝色方块"
```

---

## 2. 必须遵守的边界

这个 app 严禁：

- import `rclpy`
- 调用 `ros2 run`
- 订阅相机、深度图、`/tf`
- 发布机械臂、夹爪或 `/cmd_vel`
- 直接调用 ROS2 service/action
- 直接调用 MoveIt / Nav2
- 用关键词、字段、正则或硬编码 `if/elif` 解析用户原始输入

正确分层：

```text
User
  -> AgenticOS 全局 LLM dispatcher
  -> color_block_grasper_agent
  -> Agentic SDK / Runtime skill
  -> Runtime permission + safety + resource lock + audit
  -> Runtime adapter / ROS2 bridge
  -> ROS2 color_block_grasper backend
  -> robot hardware
```

---

## 3. 基于模板的目标目录结构

先复制模板：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_apps
cp -r app_template color_block_grasper_agent
```

复制后，目标结构应基于模板扩展为：

```text
color_block_grasper_agent/
  README.md
  app.yaml
  main.py
  context/
    color_block_context.schema.json        # 新增
    default_context.yaml                   # 新增
  memory/
    memory_keys.yaml                       # 新增
  models/
    edge_lora/
  prompts/
    system.md
  rules/
    plan.schema.json                       # 新增
    result.schema.json                     # 新增
    validation.py                          # 新增
  skills/
    color_block.grasp.yaml                 # 新增
    color_block.place.yaml                 # 新增
  storage/
    .gitkeep
  tests/
    test_manifest.py                       # 新增
    test_planner_mock.py                   # 新增
    test_validation.py                     # 新增
    test_main_mock.py                      # 新增
    test_no_direct_ros_access.py           # 新增
  tools/
    planner.py                             # 新增
    result_store.py                        # 新增
    context_builder.py                     # 新增
  workflows/
    default.yaml
```

注意：

- `planner.py`、`validation.py`、`result_store.py` 不是模板自带文件，是本 app 需要后新增的实现文件。
- 新增文件必须放在模板已有目录下。
- `models/edge_lora/` 本方案暂不使用，可以保持为空。

---

## 4. 一次抓取到底怎么发生

以“夹取蓝色方块”为例：

```text
1. 用户输入：“夹取蓝色方块”
2. 平台全局 LLM dispatcher 判断应交给 color_block_grasper_agent
3. Runtime 加载 color_block_grasper_agent/app.yaml
4. Runtime 调用 color_block_grasper_agent/main.py::run(ctx, **kwargs)
5. main.py 把已分配 task 交给 tools/planner.py
6. tools/planner.py 使用 prompts/system.md 让 app-level LLM 生成 JSON plan
7. rules/validation.py 校验 plan
8. main.py 执行 validated plan
9. 抓取 step 调用 ctx.call_skill("color_block.grasp", args)
10. Runtime 做权限、安全、资源锁、审计
11. Runtime adapter / bridge 调 ROS2 抓取后端
12. main.py 写 memory、storage、report
13. 返回 structured result
```

真正触发抓取的代码只应出现在 `main.py` 的执行阶段：

```python
result = await ctx.call_skill("color_block.grasp", args)
```

放置方块：

```python
result = await ctx.call_skill("color_block.place", args)
```

这两行不是 ROS2 调用。它们调用的是 AgenticOS Runtime skill。

---

## 5. 谁写什么

| 部分 | 谁负责 | 文件位置 | 做什么 |
| --- | --- | --- | --- |
| 全局 LLM dispatcher | 平台 / Runtime | 不在本 app 内 | 从用户输入选择 app |
| App-level planner | app 开发者 | `tools/planner.py` + `prompts/system.md` | 把已分配 task 变成抓取/放置 plan |
| Plan rules | app 开发者 | `rules/` | 校验颜色、动作、dry-run、真实运动授权 |
| App entry | app 开发者 | `main.py` | 执行 validated plan，调用 Runtime skill |
| Context 管理 | app 开发者 | `context/` + `tools/context_builder.py` | 管理本次 run 的 app-local context |
| Memory 管理 | app 开发者 | `memory/` + `ctx.memory` | 记录最后一次抓取结果等长期信息 |
| Storage 管理 | app 开发者 | `storage/` + `tools/result_store.py` | 写 app-owned run 输出 |
| Runtime skill executor | Runtime 团队 | Agentic Runtime | 权限、安全、锁、审计、超时 |
| ROS2 抓取后端 | ROS2 能力开发者 | `ros2_ws/src/color_block_grasper` | 视觉、IK、servo、夹爪动作 |

---

## 6. 模板文件逐项开发方案

### 6.1 `README.md`

写清楚：

- 这是 Agentic App，不是 ROS2 package。
- 支持红、蓝、绿方块抓取和放置。
- 默认 dry-run。
- 真实动作需要 `AGENTIC_COLOR_BLOCK_GRASPER_ALLOW_MOTION=1` 和 Runtime confirmation。
- app 不直接调用 ROS2。
- demo 命令。

### 6.2 `app.yaml`

从模板改成：

```yaml
name: color_block_grasper_agent
version: 0.1.0
description: AgenticOS app for safe color block grasp and place tasks.
entrypoint: main:run

permissions:
  - report.say
  - memory.read
  - memory.write
  - human.ask
  - color_block.manipulate

required_capabilities:
  - report.say
  - memory.recall
  - memory.remember
  - human.ask
  - color_block.grasp
  - color_block.place

safety_policy:
  allow_autonomous_navigation: false
  allow_manipulation: false
  require_human_confirmation_for:
    - color_block.grasp
    - color_block.place
  forbidden_zones: []
  max_task_duration_s: 120

runtime_limits:
  max_concurrent_tasks: 1
  max_retries_per_skill: 0
  max_memory_write_per_task: 4
  llm_planning_enabled: true
```

说明：

- `allow_manipulation: false` 表示默认不允许真实运动。
- 真实 motion 必须由 Runtime flag、环境变量和 human confirmation 一起放行。
- app 不因为 `app.yaml` 声明能力就能绕过 Runtime。

### 6.3 `prompts/system.md`

改成 app-level planner prompt。

必须包含：

```text
你是 color_block_grasper_agent 的 app-level execution planner。
平台已经选择了本 app，你不负责选择 app。
你只能输出 JSON plan。
你不能输出 ROS2 命令、shell 命令、Python 代码、topic、service、action 名称。
你只能使用这些动作：color_block_grasp、color_block_place、ask_clarification。
颜色只能是：red、blue、green。
默认 dry_run=true。
真实 motion 只有在 Runtime task 明确授权时才允许 dry_run=false。
不确定颜色或动作时，输出 ask_clarification。
```

禁止在 prompt 中鼓励 LLM 直接执行机器人动作。

### 6.4 `workflows/default.yaml`

从模板：

```yaml
name: default
version: 0.1.0
steps: []
```

改成：

```yaml
name: default
version: 0.1.0
steps:
  - id: build_context
    uses: tools.context_builder
  - id: plan
    uses: tools.planner
  - id: validate
    uses: rules.validation
  - id: execute
    uses: main.execute_validated_plan
  - id: store_result
    uses: tools.result_store
```

这是 app 内部流程描述，不是 ROS2 launch。

---

## 7. 模板目录逐项开发方案

### 7.1 `context/`

新增：

```text
context/color_block_context.schema.json
context/default_context.yaml
```

`context/color_block_context.schema.json` 定义：

```json
{
  "type": "object",
  "required": ["app_id", "session_id", "plan_id", "dry_run_default", "allowed_colors"],
  "properties": {
    "app_id": {"const": "color_block_grasper_agent"},
    "session_id": {"type": "string"},
    "plan_id": {"type": "string"},
    "dry_run_default": {"type": "boolean"},
    "allowed_colors": {
      "type": "array",
      "items": {"enum": ["red", "blue", "green"]}
    },
    "allow_motion_env": {"const": "AGENTIC_COLOR_BLOCK_GRASPER_ALLOW_MOTION"},
    "storage_run_dir": {"type": "string"}
  }
}
```

`context/default_context.yaml`：

```yaml
app_id: color_block_grasper_agent
dry_run_default: true
allowed_colors:
  - red
  - blue
  - green
allow_motion_env: AGENTIC_COLOR_BLOCK_GRASPER_ALLOW_MOTION
```

`tools/context_builder.py` 读取：

- `ctx.session_id`
- `ctx.app_manifest`
- Runtime task 中的 dry-run / real flags

它生成 app-local run context，但不创建 Runtime session。

### 7.2 `memory/`

新增：

```text
memory/memory_keys.yaml
```

内容：

```yaml
keys:
  last_color_block_plan:
    scope: app
    value_type: object
    write_when: plan_validated
  last_color_block_result:
    scope: app
    value_type: object
    write_when: task_finished
  last_grasped_color:
    scope: app
    value_type: string
    allowed_values: [red, blue, green]
    write_when: grasp_success
  color_block_failure_count:
    scope: app
    value_type: integer
    write_when: task_failed
```

实际代码只能用：

```python
await ctx.memory.recall("last_color_block_result")
await ctx.memory.remember("last_color_block_result", result)
```

不要把图像、点云、ROS2 log 写入 memory。

### 7.3 `rules/`

新增：

```text
rules/plan.schema.json
rules/result.schema.json
rules/validation.py
```

`plan.schema.json` 要约束：

```json
{
  "type": "object",
  "required": ["plan_id", "intent", "dry_run", "steps"],
  "properties": {
    "plan_id": {"type": "string"},
    "intent": {
      "enum": ["color_block_grasp", "color_block_place", "ask_clarification"]
    },
    "dry_run": {"type": "boolean"},
    "steps": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["type"],
        "properties": {
          "type": {
            "enum": ["color_block_grasp", "color_block_place", "ask_clarification"]
          },
          "color": {"enum": ["red", "blue", "green"]},
          "target": {"enum": ["workspace"]},
          "timeout_s": {"type": "integer", "minimum": 1, "maximum": 120},
          "question": {"type": "string"}
        }
      }
    }
  }
}
```

`validation.py` 做确定性校验：

- JSON schema 校验。
- `color_block_grasp` 必须有 `color`。
- `color_block_place` 不允许带未知 target。
- `dry_run=false` 时必须满足 Runtime real flag、环境变量、human confirmation。
- 颜色只能是 `red|blue|green`。
- step type 只能来自 schema。
- timeout 不超过 `app.yaml` 的 `max_task_duration_s`。

`validation.py` 不能做用户输入关键词解析。

### 7.4 `skills/`

新增：

```text
skills/color_block.grasp.yaml
skills/color_block.place.yaml
```

`skills/color_block.grasp.yaml`：

```yaml
name: color_block.grasp
version: 0.1.0
description: Grasp one visible color block through AgenticOS Runtime.
input_schema:
  type: object
  required: [color, dry_run]
  properties:
    color:
      enum: [red, blue, green]
    dry_run:
      type: boolean
    timeout_s:
      type: integer
      minimum: 1
      maximum: 120
required_permissions:
  - color_block.manipulate
required_resources:
  - camera
  - arm
  - gripper
safety:
  requires_human_confirmation_when:
    dry_run: false
audit:
  enabled: true
```

`skills/color_block.place.yaml`：

```yaml
name: color_block.place
version: 0.1.0
description: Place the currently held block through AgenticOS Runtime.
input_schema:
  type: object
  required: [dry_run]
  properties:
    dry_run:
      type: boolean
    timeout_s:
      type: integer
      minimum: 1
      maximum: 120
required_permissions:
  - color_block.manipulate
required_resources:
  - arm
  - gripper
safety:
  requires_human_confirmation_when:
    dry_run: false
audit:
  enabled: true
```

这些文件只是 skill 合同声明，不实现 ROS2 抓取。

### 7.5 `tools/`

新增：

```text
tools/planner.py
tools/context_builder.py
tools/result_store.py
```

`tools/planner.py`：

- 读取 `prompts/system.md`。
- 接收 Runtime 已分配给本 app 的 task。
- 调用 Runtime 提供的 LLM 接口。
- 要求 LLM 输出 JSON plan。
- 不调用抓取。
- 不访问 ROS2。
- 不做关键词匹配。

伪代码：

```python
async def make_plan(ctx, task, app_context):
    system_prompt = load_prompt("prompts/system.md")
    response = await ctx.llm.chat(
        system=system_prompt,
        messages=[{"role": "user", "content": task}],
        response_format={"type": "json_object"},
    )
    return parse_json(response)
```

如果当前 SDK 还没有 `ctx.llm.chat`，实现时应接入 Runtime 已有 LLM planning 服务；不能退回关键词匹配。

`tools/result_store.py`：

```text
storage/runs/<session_id>/
  manifest.json
  plan.json
  steps.jsonl
  result.json
```

`tools/context_builder.py`：

- 生成 `plan_id`。
- 生成 run storage dir。
- 合并默认 context 和 Runtime context。

### 7.6 `storage/`

保留：

```text
storage/.gitkeep
```

运行时写：

```text
storage/runs/<session_id>/
  manifest.json
  plan.json
  steps.jsonl
  result.json
```

不要写 Runtime evidence 目录，不要保存 ROS2 raw bag、raw image、raw point cloud。

### 7.7 `tests/`

新增：

```text
tests/test_manifest.py
tests/test_planner_mock.py
tests/test_validation.py
tests/test_main_mock.py
tests/test_no_direct_ros_access.py
```

测试重点：

- manifest 权限最小化。
- planner mock 输出必须是 JSON plan。
- validation 拒绝非法颜色。
- validation 拒绝未授权真实 motion。
- main mock 中只调用 `ctx.call_skill("color_block.grasp", ...)` 或 `ctx.call_skill("color_block.place", ...)`。
- 静态扫描 app 代码中没有 `rclpy`、`ros2 run`、`/cmd_vel`、`/scan`、`/odom`、`/tf`、MoveIt/Nav2 直接调用。

---

## 8. `main.py` 执行骨架

`main.py` 保持模板入口形式：

```python
from agentic_runtime.sdk import AgentContext

from rules.validation import validate_plan
from tools.context_builder import build_app_context
from tools.planner import make_plan
from tools.result_store import store_result, store_step


async def run(ctx: AgentContext, **kwargs):
    task = kwargs.get("task") or kwargs

    app_context = build_app_context(ctx, task)
    plan = await make_plan(ctx, task, app_context)
    validated_plan = validate_plan(ctx, plan, app_context)

    await ctx.memory.remember("last_color_block_plan", validated_plan)

    step_results = []
    for step in validated_plan["steps"]:
        if step["type"] == "ask_clarification":
            answer = await ctx.human.ask(step["question"])
            step_result = {"success": True, "type": "ask_clarification", "answer": answer}

        elif step["type"] == "color_block_grasp":
            args = {
                "color": step["color"],
                "dry_run": validated_plan["dry_run"],
                "timeout_s": step.get("timeout_s", 90),
            }
            step_result = await ctx.call_skill("color_block.grasp", args)

        elif step["type"] == "color_block_place":
            args = {
                "dry_run": validated_plan["dry_run"],
                "timeout_s": step.get("timeout_s", 90),
            }
            step_result = await ctx.call_skill("color_block.place", args)

        else:
            raise ValueError(f"unsupported validated step type: {step['type']}")

        await store_step(app_context, step, step_result)
        step_results.append(step_result)

    result = {
        "success": all(r.get("success", False) for r in step_results),
        "plan_id": validated_plan["plan_id"],
        "dry_run": validated_plan["dry_run"],
        "steps": step_results,
    }

    await ctx.memory.remember("last_color_block_result", result)
    await store_result(app_context, validated_plan, result)
    await ctx.report.say("color_block_grasper_agent finished")

    return result
```

这里允许按 `step["type"]` 分支，因为 `step` 已经是 LLM plan 经过 `rules/validation.py` 校验后的受控结构。

---

## 9. Context、Memory、Rules、Storage 对照

| 管理项 | 本 app 文件 | 运行时行为 |
| --- | --- | --- |
| Context | `context/color_block_context.schema.json`、`context/default_context.yaml`、`tools/context_builder.py` | 每次 run 建立 `app_id/session_id/plan_id/dry_run/storage_run_dir` |
| Memory | `memory/memory_keys.yaml` | 成功或失败后写 `last_color_block_result` 等 key |
| Rules | `rules/plan.schema.json`、`rules/result.schema.json`、`rules/validation.py` | 拒绝非法颜色、非法 step、未授权真实 motion |
| Storage | `storage/.gitkeep`、`tools/result_store.py` | 写 `manifest.json/plan.json/steps.jsonl/result.json` |

---

## 10. AgenticOS 接口与 ROS2 接口

### App 可以用的 AgenticOS 接口

本 app 使用：

```python
await ctx.report.say(...)
await ctx.memory.recall(...)
await ctx.memory.remember(...)
await ctx.human.ask(...)
await ctx.call_skill("color_block.grasp", args)
await ctx.call_skill("color_block.place", args)
```

`ctx.call_skill(...)` 必须经过 Runtime：

```text
SkillExecutor
  -> schema validation
  -> permission check
  -> safety guard
  -> resource lock
  -> audit log
  -> dispatcher / adapter
```

### App 不能用的 ROS2 接口

本 app 不能出现：

```text
import rclpy
ros2 run
ros2 topic
ros2 service
ros2 action
/cmd_vel
/scan
/odom
/tf
move_group
nav2
```

ROS2 相关内容只允许在 Runtime adapter / ROS2 bridge / ROS2 backend 中出现。

---

## 11. 测试命令

文档交付后，真正实现时至少运行：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python -m pytest agentic_apps/color_block_grasper_agent/tests -q
```

静态边界检查：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
rg -n "rclpy|ros2 run|ros2 topic|ros2 service|ros2 action|/cmd_vel|/scan|/odom|/tf|move_group|nav2" \
  agentic_apps/color_block_grasper_agent
```

预期：静态检查只允许在 README 或测试里出现禁止词说明，不允许在执行代码里出现。

---

## 12. Codex Goal 文本

可直接使用：

```text
goal:
请基于 /home/ubuntu/Agentic_OS_ROS_publish/agentic_apps/app_template
实现 /home/ubuntu/Agentic_OS_ROS_publish/agentic_apps/color_block_grasper_agent。

要求：
1. 必须从 app_template 的真实目录结构开发，不要凭空创建另一套 app 架构。
2. 新增 planner、validation、context_builder、result_store 等文件时，必须放在模板已有目录 tools/、rules/、context/、memory/、storage/、tests/ 下，并说明它们是新增实现文件。
3. 全局 LLM dispatcher 由平台负责，本 app 不实现全局路由。
4. 本 app 只实现 app-level execution planner。
5. 用户输入只能交给 LLM planner，严禁关键词、字段、正则或硬编码 if/elif 解析用户输入。
6. planner 只生成 JSON plan，不调用机器人。
7. rules 只校验 LLM plan，不解析用户输入。
8. main.py 只执行 validated plan，并通过 ctx.call_skill("color_block.grasp", args) 和 ctx.call_skill("color_block.place", args) 调 Runtime skill。
9. Agent App 中严禁 import rclpy、调用 ros2 CLI、直接访问 ROS2 topic/service/action、直接调用 MoveIt/Nav2。
10. 必须实现 context、memory、rules、storage 的文件和测试。
11. 必须包含 no direct ROS access 静态测试。
12. 最后列出改动文件、运行命令、测试结果、剩余风险和下一步。
```

---

## 13. 分阶段实施

### Phase 1: 从模板复制

- 复制 `app_template` 到 `color_block_grasper_agent`。
- 删除 Python 缓存目录。
- 更新 `README.md`、`app.yaml`、`prompts/system.md`。

### Phase 2: 补齐管理目录

- `context/`：新增 context schema 和默认 context。
- `memory/`：新增 memory key 定义。
- `rules/`：新增 plan/result schema 和 validation。
- `storage/`：保留 `.gitkeep`，实现 run 输出格式。

### Phase 3: 实现 app-level planner

- 在 `tools/planner.py` 中接 Runtime LLM。
- 只输出 JSON plan。
- 不允许 rule-based fallback。

### Phase 4: 实现执行

- 在 `main.py` 中调用 planner。
- 校验 plan。
- 执行 `ctx.call_skill("color_block.grasp", args)` 或 `ctx.call_skill("color_block.place", args)`。
- 写 memory、storage、report。

### Phase 5: 测试

- manifest 测试。
- planner mock 测试。
- validation 测试。
- main mock 测试。
- no direct ROS access 测试。

---

## 14. 完成定义

完成时必须满足：

- app 从 `app_template` 派生。
- 每个模板目录用途清楚。
- `app.yaml` 权限最小化。
- 用户输入只进入 LLM planner。
- 无 rule-based fallback。
- 抓取只通过 `ctx.call_skill("color_block.grasp", args)`。
- 放置只通过 `ctx.call_skill("color_block.place", args)`。
- app 代码中没有直接 ROS2 调用。
- context、memory、rules、storage 都有明确文件。
- tests 通过。

---

## 15. 主要风险

- 当前 SDK 如果还没有正式 `ctx.llm.chat`，需要先接 Runtime 的 LLM planning 服务；不能临时写关键词匹配。
- `ctx.call_skill("color_block.grasp", ...)` 必须确认 Runtime skill 已注册。
- 真实运动前必须确认 permission、safety、resource lock、audit 都在 Runtime 中生效。
- dry-run 与 real-run 的行为必须在测试里分开覆盖。
