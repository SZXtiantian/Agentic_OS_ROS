# How to Develop Agent Apps

This section walks through a complete Agent App from scratch. We will build a **color block grasping agent**: the user says "pick the green block and place it at the workspace tray"; the app understands the task, asks for confirmation, calls visual perception, controls arm and gripper capabilities through Runtime, verifies that the block is actually held, places it, and persists the execution record.

This app is not a ROS2 node. It does not subscribe to camera topics, call MoveIt directly, or publish `/cmd_vel`. It only orchestrates the task. Every real robot action goes through Runtime SDK and system skills, where permissions, resource locks, safety guards, and audit logs are enforced.

## What the User Does

The user provides a natural-language task:

```text
Pick the green block and place it at the workspace tray.
```

The app must:

1. Ask the Runtime LLM to convert the sentence into a structured plan.
2. Validate that the plan uses allowed colors and allowed steps.
3. Check that the app manifest grants the required permissions.
4. Ask for human confirmation because real pick-and-place is high risk.
5. Check robot, arm, gripper, and perception backend readiness.
6. Call perception system skills to find the requested colored block.
7. Call arm/gripper/manipulation system skills to pick the block.
8. Verify that the block is visibly held.
9. Place the block at the requested target.
10. Store the result in memory/storage and report completion.

Failures must be structured:

```json
{
  "success": false,
  "error_code": "COLOR_BLOCK_DETECTION_INVALID",
  "reason": "color block detection data is incomplete",
  "missing": ["center_px", "camera_position_m"],
  "next_action": "Verify the perception bridge returns validated detection fields."
}
```

## Files to Create

A maintainable Agent App uses this shape:

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

| File | Purpose |
| --- | --- |
| `app.yaml` | Declares app name, entrypoint, permissions, required capabilities, resources, and safety policy |
| `main.py` | Orchestrates planning, validation, skill calls, error handling, and result persistence |
| `prompts/system.md` | Constrains the LLM to return a JSON plan |
| `workflows/default.yaml` | Documents the task steps for developers and runtime tooling |
| `skills/find_best_block/SKILL.md` | Contract for an app-private skill |
| `skills/find_best_block/impl.py` | Python backend for the app-private skill |
| `storage/.gitkeep` | Keeps the app storage directory present |
| `tests/` | Tests manifest, boundaries, error paths, and real dependency behavior |

## Step 1: Define the Task Boundary

Before writing code, define the exact job. This app only handles color block pick-and-place.

Input:

```text
A natural-language task such as "pick the green block and place it on the tray"
```

Allowed colors:

```text
red, green, blue, yellow
```

Allowed targets:

```text
workspace or a place target allowed by the app manifest
```

Output:

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

Boundaries:

- The LLM plans only; it never controls the robot directly.
- The app does not implement a ROS2 bridge.
- The app does not call camera, arm, gripper, or MoveIt APIs directly.
- Perception, pick, and place go through system skills.
- App skills are allowed for app-private pure logic, such as ranking block candidates.

## Step 2: Write app.yaml

`app.yaml` is the Runtime contract that decides which capabilities the app may call.

```yaml
name: color_block_grasper_agent
version: 0.1.0
description: Detect, pick, verify, and place a requested color block through Runtime-controlled robot capabilities.
entrypoint: main:run
```

`entrypoint: main:run` tells Runtime to load `main.py` and call `run(ctx, **kwargs)`.

Declare permissions:

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

Permissions must match code. If the code calls `manipulation.pick_color_block`, the manifest must include `manipulation.pick.color_block`.

Declare resources:

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

Runtime and skill contracts use these resources for locking. A pick operation can lock `arm`, `gripper`, `camera`, and `manipulation_backend` so two tasks cannot use the same hardware at once.

Declare safety policy:

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

This app does not allow autonomous navigation. It allows controlled manipulation, but pick, place, gripper, and arm actions require confirmation.

## Step 3: Write the Entrypoint

Runtime injects `AgentContext`:

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    ...
```

Read the user task first:

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

Do not invent a task when input is missing. This app is designed around LLM planning from the user request.

## Step 4: Use the LLM for Planning Only

Call the Runtime LLM facade:

```python
plan_result = await ctx.llm.chat_json(
    system_prompt=_system_prompt(),
    user_prompt=f"User task: {task_text}",
    timeout_s=30,
)
```

The system prompt requires a JSON object:

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

Then validate deterministically:

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

The LLM may decide that the user wants the green block. It must not decide to skip confirmation or move the arm directly. Code and Runtime policy enforce those boundaries.

## Step 5: Convert the Plan into an Internal Task

After validation, create the internal task object:

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

This task object feeds every later step: perception needs `color`, pick needs detection, place needs `place_target`, and result persistence records the whole task.

## Step 6: Check Permissions and Ask for Confirmation

Before execution, verify required manifest permissions:

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

Then ask the operator to confirm real manipulation:

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

Continue only when the answer is `CONFIRM`. Otherwise return `COLOR_BLOCK_CONFIRMATION_REQUIRED`.

## Step 7: Wrap System Skill Calls

Use one helper so every step preserves audit data:

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

All perception, arm, gripper, pick, and place operations should go through this helper.

## Step 8: Implement Visual Recognition

Visual recognition has three layers:

| Layer | Responsibility | Location |
| --- | --- | --- |
| App orchestration | Decides which color to detect, when to capture evidence, and how to validate outputs | `main.py` |
| System skill contract | Defines inputs, outputs, permissions, locks, and safety constraints | `agentic_runtime_src/system_skills/perception.*` |
| Bridge/backend | Calls the camera, detection algorithm, or ROS2 service | ROS2 bridge workspace |

The app does not read the camera directly. It calls a system skill:

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

`perception.center_color_block` brings the requested color block into a usable camera/grasping region. The implementation may use camera data, preset arm poses, or a perception backend, but those details stay behind Runtime/bridge.

Then detect the target block:

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

The detection must prove the target location:

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

The app must validate these fields. If color, center, confidence, or camera position is missing, return `COLOR_BLOCK_DETECTION_INVALID` and do not pick.

Capture evidence through another system skill:

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

This gives developers a storage artifact to debug what the robot saw before pick.

## Step 9: Implement an App Skill for Private Logic

If the perception backend returns multiple candidate blocks, the app can use a private skill to select the best candidate. This logic belongs to this app and should not be a global system skill.

Create:

```text
skills/find_best_block/
  SKILL.md
  impl.py
```

`SKILL.md`:

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

`impl.py`:

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

This app skill only ranks candidates. It does not move the robot, so it has no permissions or resource locks. Real camera, arm, gripper, pick, and place work must remain in system skills.

## Step 10: Implement Pick

Check robot and manipulation readiness first:

```python
robot = await call_skill(ctx, steps, "check_robot", "robot.get_state", {})
arm = await call_skill(ctx, steps, "check_arm_gripper", "arm.get_state", {})
```

If robot state or gripper backend is unavailable, return:

```text
UNVERIFIED_REAL_DEPENDENCY
MANIPULATION_BACKEND_UNAVAILABLE
```

Move the arm to a known pose before perception and pick:

```python
prepare = await call_skill(
    ctx,
    steps,
    "prepare_arm_pose",
    "arm.move_named",
    {"name": "arm_home", "timeout_s": 8, "_kernel_timeout_s": 20},
)
```

Pick the block:

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

`manipulation.pick_color_block` is a system skill. Its contract declares:

- permission `manipulation.pick.color_block`
- locks for `arm`, `gripper`, `camera`, and `manipulation_backend`
- safety checks such as estop released, workspace bounds, and maximum duration
- feedback, result, and audit recording

The app passes what to pick and the validated visual location. It does not control motors or call MoveIt.

## Step 11: Verify After Pick

A successful pick call is not enough. Move the arm back to a safe pose while keeping the gripper closed:

```python
reset = await call_skill(
    ctx,
    steps,
    "reset_arm_home_holding_gripper",
    "arm.move_named",
    {"name": "arm_home", "timeout_s": 8, "_kernel_timeout_s": 20},
)
```

Then independently verify the held block:

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

The result must include `verified_held: true`. If the target color is not visible in the gripper-held region, return `COLOR_BLOCK_PICK_VERIFICATION_FAILED`.

A stronger implementation captures and verifies again after a short delay to prove the block did not slip.

## Step 12: Place the Block

Place uses another system skill:

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

`place_target` comes from the validated LLM plan. The app should not pass raw Nav2 or MoveIt poses.

## Step 13: Persist and Report

At task start, write context and a start record:

```python
await ctx.kernel.context.put("color_block_grasper.task", task, timeout_s=5)
await ctx.kernel.storage.write(
    f"color_block_grasper_agent/{ctx.session_id}_start.json",
    task,
    timeout_s=5,
)
```

At task end, persist the result:

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

`syscall_ids` and `audit_ids` are essential for debugging. They let developers trace which backend was called and what error or result it returned.

## Step 14: Write the Workflow File

`workflows/default.yaml` does not replace code, but it makes the sequence easy to inspect:

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

## Step 15: Write Tests

Cover at least:

| Test | Purpose |
| --- | --- |
| manifest tests | Ensure `app.yaml` has entrypoint, permissions, resources, and safety policy |
| boundary tests | Ensure the app does not import ROS2 or call ROS2/Nav2/MoveIt directly |
| LLM plan tests | Missing fields, unsupported colors, and wrong steps return structured errors |
| capability unavailable tests | Missing backends do not produce fake success |
| skill tests | `app.find_best_block` selects the best candidate and handles empty candidates |

Run:

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
```

## Done Checklist

Before committing:

- The app can create a JSON plan from a natural-language task.
- The LLM plan passes deterministic schema and step validation.
- `app.yaml` permissions match the code.
- Real pick requires human confirmation.
- Visual recognition uses perception system skills, not direct ROS2 topics.
- Pick and place use manipulation system skills, not direct MoveIt calls.
- App skills include both `SKILL.md` and backend implementation code.
- Every failure returns structured `error_code`, `reason`, `missing`, and `next_action`.
- Results include `syscall_ids` and `audit_ids`.
- Tests and boundary checks pass.

## Forbidden

Agent Apps must not:

- `import rclpy`
- publish `/cmd_vel`
- subscribe to `/scan`, `/odom`, or `/tf` directly
- call Nav2 or MoveIt actions directly
- call ROS2 bridge source packages directly
- let LLM logic perform realtime closed-loop control
- bypass Runtime permissions, resource locks, safety guards, or audit logs
