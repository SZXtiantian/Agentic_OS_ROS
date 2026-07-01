# 如何开发 Agent App

这一节完整演示如何从零开发一个 Agent App。我们要开发的 Agent 叫 **彩色积木抓取 Agent**：用户用自然语言说“把绿色积木抓起来并放到工作区托盘”，Agent 负责理解任务、确认风险、调用视觉识别、控制机械臂和夹爪完成抓取，再验证积木确实被夹住，最后放到指定位置并保存执行记录。

这个 Agent 不是 ROS2 节点，不直接订阅相机 topic，不直接调用 MoveIt，也不自己发布 `/cmd_vel`。它只做任务编排：所有真实机器人动作都通过 Runtime 的 SDK 和 system skills 进入权限检查、资源锁、安全守卫和审计日志。

## 最终用户会怎么用

用户给 App 一句话：

```text
Pick the green block and place it at the workspace tray.
```

App 预期完成的事情：

1. 让 Runtime LLM 把这句话转换成结构化计划。
2. 校验计划只能选择允许的颜色和步骤。
3. 检查 App manifest 是否声明了所需权限。
4. 请求人工确认，因为真实抓取和放置属于高风险动作。
5. 检查机器人、机械臂、夹爪和视觉 backend 是否可用。
6. 通过感知 system skill 让相机找到目标颜色积木。
7. 通过机械臂和夹爪 system skill 抓起积木。
8. 通过视觉 system skill 验证积木确实被夹住。
9. 将积木放到目标位置。
10. 把结果写入 memory、storage，并通过 report 输出状态。

失败时也要返回结构化错误，例如：

```json
{
  "success": false,
  "error_code": "COLOR_BLOCK_DETECTION_INVALID",
  "reason": "color block detection data is incomplete",
  "missing": ["center_px", "camera_position_m"],
  "next_action": "Verify the perception bridge returns validated detection fields."
}
```

## 要创建哪些文件

一个可维护的 Agent App 至少包含这些文件：

```text
agentic_apps/color_block_grasper_agent/
  app.yaml
  main.py
  prompts/system.md
  workflows/default.yaml
  skills/find_best_block/
    SKILL.md
    impl.py
  storage/.gitkeep
  tests/
```

每个文件的作用：

| 文件 | 作用 |
| --- | --- |
| `app.yaml` | 声明 App 名称、入口函数、权限、所需能力、资源和安全策略 |
| `main.py` | Agent 的主流程，负责任务解析、校验、skill 调用、错误处理和结果保存 |
| `prompts/system.md` | 给 LLM 的规划提示词，约束它必须返回 JSON plan |
| `workflows/default.yaml` | 给开发者和运行时工具看的步骤清单 |
| `skills/find_best_block/SKILL.md` | App 私有 skill 的 contract |
| `skills/find_best_block/impl.py` | App 私有 skill 的 Python 后端实现 |
| `storage/.gitkeep` | 保留 App storage 目录 |
| `tests/` | manifest、边界、错误码和真实依赖测试 |

## 第一步：定义 Agent 要解决的问题

先不要写代码，先定义任务边界。这个 Agent 只解决“彩色积木抓取和放置”：

输入：

```text
用户自然语言任务，例如“抓取绿色积木并放到托盘”
```

允许的颜色：

```text
red, green, blue, yellow
```

允许的目标：

```text
workspace 或 App manifest 中允许的 place target
```

输出：

```json
{
  "success": true,
  "planner_mode": "llm",
  "detection": {},
  "pick": {},
  "post_pick_verification": {},
  "place": {},
  "syscall_ids": [],
  "audit_ids": []
}
```

边界：

- LLM 只能做规划，不能直接控制机器人。
- App 不实现 ROS2 bridge。
- App 不直接调用相机、机械臂、夹爪或 MoveIt。
- 视觉识别、抓取、放置都通过 system skill。
- App 可以写 app skill 做本应用内部的纯业务逻辑，例如候选积木排序。

## 第二步：写 app.yaml

`app.yaml` 是 Runtime 判断这个 App 能不能调用某项能力的依据。写 App 时，先把它需要的能力写清楚。

```yaml
name: color_block_grasper_agent
version: 0.1.0
description: Detect, pick, verify, and place a requested color block through Runtime-controlled robot capabilities.
entrypoint: main:run
```

`entrypoint: main:run` 表示 Runtime 会加载 `main.py`，调用里面的 `run(ctx, **kwargs)`。

接着声明权限：

```yaml
permissions:
  - llm.external.call
  - robot.state.read
  - robot.stop
  - perception.observe
  - perception.capture
  - perception.detect.color_block
  - perception.center.color_block
  - perception.verify.color_block_held
  - arm.state.read
  - arm.move.named
  - gripper.control
  - manipulation.pick.color_block
  - manipulation.place.color_block
  - human.ask
  - context.write
  - context.read
  - memory.write
  - memory.read
  - storage.read
  - storage.write
  - report.say
```

这些权限和代码里的调用要一一对应。例如代码里调用 `manipulation.pick_color_block`，manifest 里就必须有 `manipulation.pick.color_block`。

再声明资源：

```yaml
resources:
  - camera
  - arm
  - gripper
  - color_block_detector
  - color_block_centering
  - held_color_block_verifier
  - manipulation_backend
```

这些资源会被 Runtime 和 skill contract 用来做资源锁。例如抓取时会锁住 `arm`、`gripper`、`camera` 和 `manipulation_backend`，避免两个任务同时抢同一套硬件。

安全策略必须明确：

```yaml
safety_policy:
  allow_autonomous_navigation: false
  allow_manipulation: true
  require_human_confirmation_for:
    - manipulation.pick_color_block
    - manipulation.place_color_block
    - gripper.set
    - arm.move_named
  forbidden_zones: []
  max_task_duration_s: 180
```

这里的含义是：这个 App 不允许自主导航，但允许受控机械臂操作；抓取、放置、夹爪和机械臂动作都必须有人确认。

## 第三步：写入口函数

入口函数固定接收 Runtime 注入的 `AgentContext`：

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    ...
```

第一件事是读取用户任务：

```python
task_text = str(
    kwargs.get("task_text")
    or kwargs.get("message")
    or kwargs.get("text")
    or ""
).strip()

if not task_text:
    return {
        "success": False,
        "error_code": "COLOR_BLOCK_LLM_PLAN_REQUIRED",
        "reason": "natural language task_text or message is required",
        "missing": ["task_text"],
        "next_action": "Provide a natural language color-block manipulation request and rerun.",
    }
```

这里不要默认替用户编造任务。没有自然语言输入就失败，因为这个 App 的设计是由 LLM 做任务规划。

## 第四步：让 LLM 输出计划，而不是控制机器人

App 调用 Runtime 提供的 LLM facade：

```python
plan_result = await ctx.llm.chat_json(
    system_prompt=_system_prompt(),
    user_prompt=f"User task: {task_text}",
    timeout_s=30,
)
```

system prompt 要求 LLM 只返回 JSON，例如：

```json
{
  "schema_version": "1.0",
  "planner_mode": "llm",
  "target_color": "green",
  "place_target": "workspace_tray",
  "requires_manipulation": true,
  "needs_confirmation": true,
  "steps": [
    "prepare_arm_pose",
    "center_color_block",
    "detect_color_block",
    "capture_evidence",
    "pick_color_block",
    "reset_arm_home_holding_gripper",
    "post_pick_verify",
    "place_color_block"
  ],
  "risk_class": "controlled_manipulation",
  "user_summary": "Pick the green block and place it at the workspace tray."
}
```

然后用确定性代码校验：

```python
ALLOWED_COLORS = {"red", "green", "blue", "yellow"}
PLAN_STEPS = [
    "prepare_arm_pose",
    "center_color_block",
    "detect_color_block",
    "capture_evidence",
    "pick_color_block",
    "reset_arm_home_holding_gripper",
    "post_pick_verify",
    "place_color_block",
]


def validate_plan(plan: dict) -> dict:
    if plan.get("schema_version") != "1.0":
        return {"success": False, "error_code": "COLOR_BLOCK_LLM_PLAN_INVALID"}
    if plan.get("target_color") not in ALLOWED_COLORS:
        return {"success": False, "error_code": "COLOR_BLOCK_LLM_PLAN_INVALID"}
    if plan.get("steps") != PLAN_STEPS:
        return {"success": False, "error_code": "COLOR_BLOCK_LLM_PLAN_INVALID"}
    if plan.get("requires_manipulation") is not True:
        return {"success": False, "error_code": "COLOR_BLOCK_LLM_PLAN_INVALID"}
    if plan.get("needs_confirmation") is not True:
        return {"success": False, "error_code": "COLOR_BLOCK_LLM_PLAN_INVALID"}
    return {"success": True}
```

关键点：LLM 可以决定“用户想抓绿色积木”，但不能决定“跳过确认”或“直接移动机械臂”。这些必须由代码和 Runtime 安全策略控制。

## 第五步：把计划转换成任务对象

验证通过后，把 plan 转成 App 内部 task：

```python
task = {
    "task_text": task_text,
    "planner_mode": "llm",
    "plan": plan,
    "color": plan["target_color"],
    "target": plan.get("target") or "workspace",
    "place_target": plan["place_target"],
    "requires_manipulation": True,
    "needs_confirmation": True,
    "evidence_label": plan.get("evidence_label") or f"{plan['target_color']}_block_grasp",
    "timeout_s": int(plan.get("timeout_s") or 180),
    "risk_class": plan["risk_class"],
}
```

这个 task 会贯穿后续所有步骤：视觉识别要知道 `color`，抓取要用 detection，放置要用 `place_target`，结果保存要记录整个 task。

## 第六步：先做权限和人工确认

代码执行前先检查 manifest 里是否有必要权限：

```python
required_permissions = [
    "perception.detect.color_block",
    "perception.center.color_block",
    "perception.capture",
    "perception.verify.color_block_held",
    "manipulation.pick.color_block",
    "manipulation.place.color_block",
    "human.ask",
]

missing = [
    permission
    for permission in required_permissions
    if permission not in ctx.app_manifest.permissions
]
if missing:
    return {
        "success": False,
        "error_code": "COLOR_BLOCK_CAPABILITY_UNAVAILABLE",
        "missing": missing,
    }
```

然后让 operator 确认真实抓取：

```python
confirmation = await ctx.kernel.skill.call(
    "human.ask",
    {
        "question": f"Confirm real manipulation: pick the {task['color']} block and place it at {task['place_target']}.",
        "options": ["CONFIRM", "CANCEL"],
        "require_confirmation": True,
        "timeout_s": 60,
    },
    timeout_s=60,
)
```

只有回答 `CONFIRM` 才继续。未确认时返回 `COLOR_BLOCK_CONFIRMATION_REQUIRED`。

## 第七步：统一封装 system skill 调用

为了让每个步骤都保留 audit 信息，建议统一写一个 helper：

```python
async def call_skill(ctx, steps, name: str, skill_name: str, args: dict) -> dict:
    result = await ctx.kernel.skill.call(skill_name, args, timeout_s=args.get("_kernel_timeout_s", 10))
    step = {
        "name": name,
        "skill": skill_name,
        "success": bool(result.success),
        "error_code": result.error_code,
        "data": result.response or {},
        "syscall_id": result.syscall_id,
        "audit_id": result.audit_id,
    }
    steps.append(step)
    return step
```

后续所有视觉、机械臂、夹爪、抓取、放置动作都通过这个 helper 调 system skill。

## 第八步：完成视觉识别

视觉识别分三层理解：

| 层 | 负责什么 | 在哪里 |
| --- | --- | --- |
| App 编排层 | 决定要识别什么颜色、何时拍照、如何校验结果 | `main.py` |
| System skill contract | 定义输入、输出、权限、资源锁、安全约束 | `agentic_runtime_src/system_skills/perception.*` |
| Bridge/backend | 真正调用相机、检测算法或 ROS2 service | ROS2 bridge workspace |

App 不直接读相机。它调用 system skill：

```python
center = await call_skill(
    ctx,
    steps,
    "center_color_block",
    "perception.center_color_block",
    {
        "color": task["color"],
        "target": task["target"],
        "evidence_label": f"{task['evidence_label']}_center",
        "timeout_s": 12,
        "_kernel_timeout_s": 45,
    },
)
```

`perception.center_color_block` 的目标是让目标颜色积木进入可抓取的视觉区域。它可能通过相机、机械臂预设姿态或视觉 backend 完成居中，但这些细节都在 Runtime/bridge 里，App 只看结构化结果。

然后检测目标积木：

```python
detection = await call_skill(
    ctx,
    steps,
    "detect_color_block",
    "perception.detect_color_block",
    {
        "color": task["color"],
        "target": task["target"],
        "evidence_label": task["evidence_label"],
        "timeout_s": 30,
        "_kernel_timeout_s": 75,
    },
)
```

检测结果至少要能证明：

```json
{
  "success": true,
  "detection": {
    "color": "green",
    "confidence": 0.92,
    "center_px": {"x": 318, "y": 221},
    "camera_position_m": {"x": 0.32, "y": 0.04, "z": 0.02}
  },
  "candidates": []
}
```

App 必须校验这些字段。如果没有颜色、中心点、置信度或相机坐标，就返回 `COLOR_BLOCK_DETECTION_INVALID`，不要继续抓取。

拍照证据也通过 system skill：

```python
evidence = await call_skill(
    ctx,
    steps,
    "capture_evidence",
    "perception.capture_photo",
    {
        "target": task["target"],
        "label": task["evidence_label"],
        "timeout_s": 15,
    },
)
```

这样开发者可以在 storage 里追踪抓取前的视觉证据。

## 第九步：写 App Skill 处理应用私有逻辑

如果视觉 backend 返回多个候选积木，App 可以写一个私有 skill 来选择最佳候选。这个逻辑只属于彩色积木抓取 App，不应该放成全局 system skill。

创建：

```text
skills/find_best_block/
  SKILL.md
  impl.py
```

`SKILL.md`：

```json
{
  "schema_version": 1,
  "name": "app.find_best_block",
  "scope": "app",
  "implementation": {
    "type": "python",
    "entrypoint": "impl:run"
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "candidates": {"type": "array"}
    },
    "required": ["candidates"]
  },
  "output_schema": {
    "type": "object",
    "required": ["success"],
    "properties": {
      "success": {"type": "boolean"},
      "selected": {"type": "object"},
      "index": {"type": "integer"}
    }
  },
  "permission_requirements": [],
  "resource_requirements": {"locks": []},
  "timeout_s": 3,
  "observability": {"audit": true}
}
```

`impl.py`：

```python
from __future__ import annotations

from typing import Any


def run(args: dict[str, Any], context=None) -> dict[str, Any]:
    candidates = args.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return {
            "success": False,
            "error_code": "COLOR_BLOCK_NOT_FOUND",
            "reason": "no color block candidates were provided",
        }

    indexed = [
        (index, candidate)
        for index, candidate in enumerate(candidates)
        if isinstance(candidate, dict)
    ]
    if not indexed:
        return {
            "success": False,
            "error_code": "COLOR_BLOCK_NOT_FOUND",
            "reason": "color block candidates must be objects",
        }

    def score(item: tuple[int, dict[str, Any]]) -> tuple[float, float]:
        _, candidate = item
        confidence = float(candidate.get("confidence", 0.0) or 0.0)
        center = candidate.get("center") if isinstance(candidate.get("center"), dict) else {}
        x = float(center.get("x", 0.5) or 0.5)
        y = float(center.get("y", 0.5) or 0.5)
        centered = 1.0 - min(abs(x - 0.5) + abs(y - 0.5), 1.0)
        return confidence, centered

    index, selected = max(indexed, key=score)
    return {"success": True, "selected": selected, "index": index}
```

这个 app skill 只做候选排序，不控制机器人，所以没有权限要求和资源锁。真正移动相机、机械臂、夹爪的动作仍然必须使用 system skill。

## 第十步：完成抓取

抓取前先检查机器人状态：

```python
robot = await call_skill(ctx, steps, "check_robot", "robot.get_state", {})
arm = await call_skill(ctx, steps, "check_arm_gripper", "arm.get_state", {})
```

如果机器人状态或夹爪 backend 不可用，返回：

```text
UNVERIFIED_REAL_DEPENDENCY
MANIPULATION_BACKEND_UNAVAILABLE
```

然后把机械臂放到可检测、可抓取的预设姿态：

```python
prepare = await call_skill(
    ctx,
    steps,
    "prepare_arm_pose",
    "arm.move_named",
    {"name": "arm_home", "timeout_s": 8, "_kernel_timeout_s": 20},
)
```

真正抓取：

```python
pick = await call_skill(
    ctx,
    steps,
    "pick_color_block",
    "manipulation.pick_color_block",
    {
        "color": task["color"],
        "target": task["target"],
        "detection": detection["data"]["validated_detection"],
        "evidence": evidence["data"],
        "timeout_s": 60,
    },
)
```

这里 `manipulation.pick_color_block` 是 system skill。它的 contract 会声明：

- 需要权限 `manipulation.pick.color_block`
- 锁住 `arm`、`gripper`、`camera`、`manipulation_backend`
- 要求安全守卫检查，例如急停释放、工作空间边界、最大时长
- 记录 feedback、result 和 audit

App 只传入“要抓什么”和“视觉检测到的位置”，不直接控制电机、不直接调用 MoveIt。

## 第十一步：抓取后验证

抓取成功并不等于任务成功。App 要把机械臂回到安全姿态，同时保持夹爪闭合：

```python
reset = await call_skill(
    ctx,
    steps,
    "reset_arm_home_holding_gripper",
    "arm.move_named",
    {"name": "arm_home", "timeout_s": 8, "_kernel_timeout_s": 20},
)
```

然后做独立视觉验证：

```python
verification = await call_skill(
    ctx,
    steps,
    "post_pick_verify",
    "perception.verify_held_color_block",
    {
        "color": task["color"],
        "target": task["target"],
        "detection": detection["data"]["validated_detection"],
        "pick_result": pick["data"],
        "evidence_label": f"{task['evidence_label']}_held_verify",
        "timeout_s": 30,
    },
)
```

验证结果必须明确 `verified_held: true`。如果看不到目标颜色积木在夹爪区域，就返回 `COLOR_BLOCK_PICK_VERIFICATION_FAILED`，不能宣布成功。

更稳妥的实现会在短暂延迟后再次拍照和验证，确认积木没有从夹爪中滑落。

## 第十二步：完成放置

放置使用另一个 system skill：

```python
place = await call_skill(
    ctx,
    steps,
    "place_color_block",
    "manipulation.place_color_block",
    {
        "color": task["color"],
        "place_target": task["place_target"],
        "pick_result": pick["data"],
        "timeout_s": 60,
    },
)
```

`place_target` 必须来自 LLM plan 并经过 App 校验。App 不应该直接传 Nav2 pose 或 MoveIt pose。

## 第十三步：保存结果和报告

任务开始时写 context 和 start record：

```python
await ctx.kernel.context.put("color_block_grasper.task", task, timeout_s=5)
await ctx.kernel.storage.write(
    f"color_block_grasper_agent/{ctx.session_id}_start.json",
    task,
    timeout_s=5,
)
```

任务结束时保存 result：

```python
result = {
    "success": True,
    "task": task,
    "steps": steps,
    "detection": detection["data"],
    "pick": pick["data"],
    "post_pick_verification": verification["data"],
    "place": place["data"],
    "syscall_ids": [step["syscall_id"] for step in steps if step.get("syscall_id")],
    "audit_ids": [step["audit_id"] for step in steps if step.get("audit_id")],
}

await ctx.kernel.memory.remember(
    result,
    key=f"{ctx.session_id}:color-block-result",
    tags=["color_block", "evidence"],
    timeout_s=5,
)
await ctx.kernel.storage.write(
    f"color_block_grasper_agent/{ctx.session_id}_result.json",
    result,
    timeout_s=5,
)
await ctx.kernel.skill.call(
    "report.say",
    {"message": f"Color block task completed for {task['color']} -> {task['place_target']}."},
    timeout_s=5,
)
```

`syscall_ids` 和 `audit_ids` 很重要。真实机器人任务出问题时，开发者可以用它们回查每一步调用了哪个 backend、拿到了什么错误。

## 第十四步：写 workflow 清单

`workflows/default.yaml` 不替代代码逻辑，但它能让开发者快速理解任务顺序：

```yaml
name: default
version: 0.1.0
steps:
  - record_context
  - check_robot
  - check_arm_gripper
  - human_confirmation
  - prepare_arm_pose
  - center_color_block
  - detect_color_block
  - capture_evidence
  - pick_color_block
  - reset_arm_home_holding_gripper
  - post_pick_gripper_state
  - capture_post_pick_evidence
  - post_pick_verify
  - capture_post_pick_stability_evidence
  - post_pick_stability_verify
  - place_color_block
  - remember_result
  - write_result
  - report_result
```

## 第十五步：写测试

至少覆盖这些测试：

| 测试 | 目的 |
| --- | --- |
| manifest 测试 | 确认 `app.yaml` 有入口、权限、资源、安全策略 |
| 边界测试 | 确认 App 没有 `import rclpy`、没有直接 ROS2/Nav2/MoveIt 调用 |
| LLM plan 测试 | 缺字段、错误颜色、错误步骤时返回结构化错误 |
| capability unavailable 测试 | backend 不存在时不能伪造成功 |
| skill 测试 | `app.find_best_block` 能选择最佳候选，并处理空候选 |

运行：

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
```

## 开发完成检查表

提交前逐项确认：

- App 可以从自然语言任务生成 JSON plan。
- LLM plan 经过确定性 schema 和步骤校验。
- `app.yaml` 权限和代码调用一致。
- 真实抓取前必须人工确认。
- 视觉识别通过 perception system skill，不直接读 ROS2 topic。
- 抓取和放置通过 manipulation system skill，不直接调用 MoveIt。
- App skill 有 `SKILL.md`，也有对应 backend 实现。
- 所有失败都返回结构化 `error_code`、`reason`、`missing`、`next_action`。
- 结果包含 `syscall_ids` 和 `audit_ids`。
- 测试和边界检查通过。

## 禁止事项

Agent App 不允许：

- `import rclpy`
- 发布 `/cmd_vel`
- 直接订阅 `/scan`、`/odom`、`/tf`
- 直接调用 Nav2 或 MoveIt action
- 直接调用 ROS2 bridge source package
- 让 LLM 做实时闭环控制
- 绕过 Runtime 权限、资源锁、安全守卫或 audit log
