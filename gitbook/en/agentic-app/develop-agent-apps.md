# How to Develop Agent Apps

Treat an Agent App as a controlled orchestration layer. It can read and write Runtime context, memory, and storage, and it can call SDK namespaces and skills. It must not touch ROS2, Nav2, MoveIt, hardware topics, or vendor drivers directly.

This page continues with:

```text
agentic_apps/color_block_grasper_agent/
```

## Directory Structure

Important files in the example app:

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

A new app should have at least:

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

## 1. Write app.yaml

`app.yaml` is the Runtime contract for deciding which capabilities the app may call. Do not call undeclared capabilities from code.

The example declares:

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

Guidelines:

- Keep `permissions` to the smallest set the app needs.
- List resources that may be locked, such as `camera`, `arm`, and `gripper`.
- Real motion must be covered by `safety_policy`, including confirmation, forbidden zones, time limits, or other constraints.
- Use `required_capabilities` to surface missing dependencies before the task is halfway through execution.

## 2. Write the Entrypoint

Entrypoint signature:

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    ...
```

The return value must be a `dict` with `success: bool`. Failures must return structured errors.

The example first reads the natural-language task:

```python
task_text = str(kwargs.get("task_text") or kwargs.get("message") or kwargs.get("text") or "").strip()
if not task_text:
    return {
        "success": False,
        "error_code": "COLOR_BLOCK_LLM_PLAN_REQUIRED",
        "missing": ["task_text"],
    }
```

## 3. Use the LLM Only for Planning

`color_block_grasper_agent` calls:

```python
result = await ctx.llm.chat_json(
    system_prompt=_system_prompt(),
    user_prompt=f"User task: {task_text}",
    timeout_s=30,
)
```

The LLM must return a JSON plan. The app then validates it with `_validate_plan(plan)`. New apps should constrain LLM output with:

- A fixed schema version.
- Explicit allowed enums for colors, places, modes, or targets.
- A fixed execution sequence.
- Explicit `requires_manipulation` and `needs_confirmation` fields.
- A `*_PLAN_INVALID` failure path when validation fails.

## 4. Convert the Plan into Controlled Skill Calls

The example uses `_call_skill(...)` to invoke system skills consistently:

```python
result = await ctx.kernel.skill.call(skill_name, call_args, timeout_s=kernel_timeout_s)
```

Examples:

```python
await ctx.kernel.skill.call("perception.center_color_block", {...})
await ctx.kernel.skill.call("perception.detect_color_block", {...})
await ctx.kernel.skill.call("manipulation.pick_color_block", {...})
await ctx.kernel.skill.call("perception.verify_held_color_block", {...})
await ctx.kernel.skill.call("manipulation.place_color_block", {...})
```

Each step goes through Runtime permissions, access/intervention, resource locks, safety constraints, timeouts, syscall records, and audit records.

## 5. Write App Skills

Skills are split into system skills and app skills. An app skill is private to the current app and is useful for logic tightly coupled to that app.

Example:

```text
skills/find_best_block/
  SKILL.md
  impl.py
```

`SKILL.md` declares:

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

`impl.py` is the backend:

```python
def run(args: dict, context=None) -> dict:
    candidates = args.get("candidates")
    ...
    return {"success": True, "selected": selected, "index": index}
```

A skill is not only a Markdown file. `SKILL.md` is the contract; the same directory must provide the backend implementation or clearly point to a Runtime/bridge-owned implementation entry.

`app.find_best_block` only ranks candidate detections and does not move the robot, so it does not need resource locks. Real motion must stay in system skills.

## 6. Persist Context, Results, and Audit Links

The example writes context and a start record:

```python
await ctx.kernel.context.put("color_block_grasper.task", task, timeout_s=5)
await ctx.kernel.storage.write(f"color_block_grasper_agent/{ctx.session_id}_start.json", task, timeout_s=5)
```

It writes memory and storage at the end:

```python
await ctx.kernel.memory.remember(result, key=f"{ctx.session_id}:color-block-result", tags=["color_block", "evidence"], timeout_s=5)
await ctx.kernel.storage.write(f"color_block_grasper_agent/{ctx.session_id}_result.json", result, timeout_s=5)
```

Keep `syscall_ids` and `audit_ids` in the result so every backend call can be traced.

## 7. Write Tests

The example tests cover:

- Required manifest fields.
- No direct ROS2 imports.
- Kernel/SDK boundaries.
- Structured errors when capabilities are unavailable.
- Template provenance and real dependency markers.

Run:

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
```

When behavior changes, update tests. This is especially important for new robot actions, perception backends, storage formats, and error codes.

## Forbidden

Agent Apps must not:

- `import rclpy`
- publish `/cmd_vel`
- subscribe to `/scan`, `/odom`, or `/tf` directly
- call Nav2 or MoveIt actions directly
- call ROS2 bridge source packages directly
- let LLM logic perform realtime closed-loop control
- bypass Runtime permissions, resource locks, safety guards, or audit logs
