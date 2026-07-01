# 如何开发 Agent App

开发 Agent App 时先把它当成“受控任务编排层”：它可以读写 Runtime context/memory/storage，可以调用 SDK 和 skill，但不能直接碰 ROS2、Nav2、MoveIt、硬件 topic 或 vendor driver。

本页继续使用：

```text
agentic_apps/color_block_grasper_agent/
```

## 目录结构

示例 App 的关键文件：

```text
agentic_apps/color_block_grasper_agent/
  README.md
  app.yaml
  main.py
  config.json
  prompts/system.md
  workflows/default.yaml
  skills/find_best_block/
    SKILL.md
    impl.py
  storage/.gitkeep
  tests/
```

开发新 App 时至少保留：

```text
agentic_apps/<your_app>/
  app.yaml
  main.py
  prompts/system.md
  workflows/default.yaml
  skills/
  storage/.gitkeep
  tests/
```

## 1. 写 app.yaml

`app.yaml` 是 Runtime 决定是否允许 App 调能力的入口。不要在代码里偷偷调用未声明能力。

示例 App 声明了：

```yaml
name: color_block_grasper_agent
entrypoint: main:run
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
resources:
  - camera
  - arm
  - gripper
  - color_block_detector
  - manipulation_backend
safety_policy:
  allow_autonomous_navigation: false
  allow_manipulation: true
  require_human_confirmation_for:
    - manipulation.pick_color_block
    - manipulation.place_color_block
    - gripper.set
    - arm.move_named
```

开发原则：

- `permissions` 只写 App 真正需要的最小集合。
- `resources` 要覆盖会被锁住的实体，例如 `camera`、`arm`、`gripper`。
- 涉及真实运动时，`safety_policy` 必须体现确认、禁区、时长或其他安全约束。
- `required_capabilities` 用来提前暴露依赖缺口，不要等任务执行到一半才发现 backend 不存在。

## 2. 写入口函数

入口函数签名：

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    ...
```

返回值必须是 `dict`，并包含 `success: bool`。失败时必须返回结构化错误。

示例 App 的第一步是取自然语言任务：

```python
task_text = str(kwargs.get("task_text") or kwargs.get("message") or kwargs.get("text") or "").strip()
if not task_text:
    return {
        "success": False,
        "error_code": "COLOR_BLOCK_LLM_PLAN_REQUIRED",
        "missing": ["task_text"],
    }
```

## 3. 让 LLM 只做规划

`color_block_grasper_agent` 调：

```python
result = await ctx.llm.chat_json(
    system_prompt=_system_prompt(),
    user_prompt=f"User task: {task_text}",
    timeout_s=30,
)
```

LLM 输出必须是 JSON plan。App 之后用 `_validate_plan(plan)` 做硬校验。开发新 App 时也建议把 LLM 输出限制为：

- 固定 schema version。
- 明确 allowed enum，例如颜色、位置、模式。
- 固定步骤序列。
- 明确 `requires_manipulation` 和 `needs_confirmation`。
- 失败时返回 `*_PLAN_INVALID`，不要继续执行。

## 4. 把计划变成受控 skill 调用

示例 App 使用 `_call_skill(...)` 统一调用 system skill：

```python
result = await ctx.kernel.skill.call(skill_name, call_args, timeout_s=kernel_timeout_s)
```

例如：

```python
await ctx.kernel.skill.call("perception.center_color_block", {...})
await ctx.kernel.skill.call("perception.detect_color_block", {...})
await ctx.kernel.skill.call("manipulation.pick_color_block", {...})
await ctx.kernel.skill.call("perception.verify_held_color_block", {...})
await ctx.kernel.skill.call("manipulation.place_color_block", {...})
```

这样每一步都会经过 Runtime 的权限检查、access/intervention、资源锁、安全约束、timeout、syscall 记录和 audit 记录。

## 5. 写 App Skill

Skill 分为 system skill 和 app skill。App skill 是当前 App 私有的小能力，适合封装和本 App 强绑定的逻辑。

示例：

```text
skills/find_best_block/
  SKILL.md
  impl.py
```

`SKILL.md` 声明：

```json
{
  "name": "app.find_best_block",
  "scope": "app",
  "implementation": {
    "type": "python",
    "entrypoint": "impl:run"
  }
}
```

`impl.py` 提供真正后端：

```python
def run(args: dict, context=None) -> dict:
    candidates = args.get("candidates")
    ...
    return {"success": True, "selected": selected, "index": index}
```

也就是说，skill 不是只放一份 Markdown。`SKILL.md` 是 contract，同目录下必须能找到对应的 backend 实现或明确指向 Runtime/bridge 拥有的实现入口。

`app.find_best_block` 只对候选检测结果排序，不移动机器人，因此不需要资源锁。真实运动仍然必须走 system skill。

## 6. 记录上下文、结果和审计线索

示例 App 在开始时写 context 和 storage：

```python
await ctx.kernel.context.put("color_block_grasper.task", task, timeout_s=5)
await ctx.kernel.storage.write(f"color_block_grasper_agent/{ctx.session_id}_start.json", task, timeout_s=5)
```

结束时写 memory 和 storage：

```python
await ctx.kernel.memory.remember(result, key=f"{ctx.session_id}:color-block-result", tags=["color_block", "evidence"], timeout_s=5)
await ctx.kernel.storage.write(f"color_block_grasper_agent/{ctx.session_id}_result.json", result, timeout_s=5)
```

结果里要保留 `syscall_ids` 和 `audit_ids`，方便排查每个 backend 调用。

## 7. 写测试

示例 App 的测试覆盖：

- manifest 必填字段。
- 禁止直接 ROS2 import。
- Kernel/SDK 边界。
- capability 不可用时返回结构化错误。
- 模板来源和真实依赖标记。

运行：

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
```

新增行为时，同步更新测试。尤其是新增机器人动作、感知 backend、存储格式和错误码时，必须加测试。

## 禁止事项

Agent App 不允许：

- `import rclpy`
- 发布 `/cmd_vel`
- 直接订阅 `/scan`、`/odom`、`/tf`
- 直接调用 Nav2 或 MoveIt action
- 直接调用 ROS2 bridge source package
- 让 LLM 做实时闭环控制
- 绕过 Runtime 权限、资源锁、安全守卫或 audit log
