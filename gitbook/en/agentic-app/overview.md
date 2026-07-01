# How to Use Agent Apps

An Agent App is orchestration code running above Agentic Runtime. It understands the user task, coordinates high-level capabilities, persists results, and reports status. It is not a ROS2 package, not a bridge node, and not a hardware driver.

This page uses the repository example:

```text
agentic_apps/color_block_grasper_agent/
```

This app takes a natural-language request, selects the requested colored block, asks for confirmation, and then calls controlled perception, arm, gripper, pick, and place capabilities.

## Entry Point

The entry point is declared in `app.yaml`:

```yaml
name: color_block_grasper_agent
entrypoint: main:run
```

Runtime injects `AgentContext` and calls `run(ctx, **kwargs)` from `main.py`. The caller should provide a natural-language task:

```python
result = await run(ctx, task_text="Pick the green block and place it at the workspace tray.")
```

The app also accepts `message` or `text`. If none is provided, it returns:

```json
{
  "success": false,
  "error_code": "COLOR_BLOCK_LLM_PLAN_REQUIRED"
}
```

## Execution Flow

`color_block_grasper_agent` does not let the LLM directly control the robot. The LLM only produces a JSON plan. Deterministic app code validates that plan before any robot capability can run.

```text
task_text
  -> ctx.llm.chat_json(...)
  -> validate plan schema
  -> validate app permissions
  -> record context and storage start record
  -> human.ask confirmation
  -> robot/arm/gripper readiness checks
  -> arm.move_named arm_home
  -> perception.center_color_block
  -> perception.detect_color_block
  -> perception.capture_photo
  -> manipulation.pick_color_block
  -> arm.move_named arm_home while holding
  -> perception.verify_held_color_block
  -> manipulation.place_color_block
  -> memory/storage/report
```

The LLM plan must include `schema_version`, `planner_mode`, `target_color`, `place_target`, `requires_manipulation`, `needs_confirmation`, `steps`, `risk_class`, and `user_summary`.

`target_color` must be one of `red`, `green`, `blue`, or `yellow`. `steps` must exactly match the deterministic sequence:

```text
prepare_arm_pose
center_color_block
detect_color_block
capture_evidence
pick_color_block
reset_arm_home_holding_gripper
post_pick_verify
place_color_block
```

If the LLM omits a field, chooses an unsupported color, or changes the step order, the app returns `COLOR_BLOCK_LLM_PLAN_INVALID` and does not continue to robot execution.

## Result Shape

A successful result contains:

- `success: true`
- `planner_mode: "llm"`
- `plan`
- `steps`
- `detection`
- `evidence`
- `pick`
- `post_pick_verification`
- `place`
- `syscall_ids`
- `audit_ids`

Failures are also structured with `error_code`, `reason`, `missing`, `next_action`, and the steps completed so far. This matters for real robot dependencies: if the perception bridge is unavailable, the app returns a capability/backend error instead of pretending the operation succeeded.

## Capabilities Used

`app.yaml` declares the permissions and capabilities the app is allowed to use:

| Category | Capabilities |
| --- | --- |
| LLM | `ctx.llm.chat_json(...)` |
| Robot | `robot.get_state`, `robot.stop` |
| Human | `human.ask` |
| Perception | `perception.center_color_block`, `perception.detect_color_block`, `perception.capture_photo`, `perception.verify_held_color_block` |
| Arm | `arm.get_state`, `arm.move_named` |
| Gripper | `gripper.set` readiness/holding checks |
| Manipulation | `manipulation.pick_color_block`, `manipulation.place_color_block` |
| Runtime state | `ctx.kernel.context.*`, `ctx.kernel.memory.*`, `ctx.kernel.storage.*` |
| Report | `report.say` |

Robot motion, perception, and arm operations go through `ctx.kernel.skill.call(...)` to system skills. The app does not import `rclpy`, publish `/cmd_vel`, or call Nav2/MoveIt directly.

## Human Confirmation

Real pick-and-place is a high-risk operation. Before execution, the app calls:

```python
await ctx.kernel.skill.call("human.ask", {...})
```

The operator must answer `CONFIRM`. Without confirmation, the app returns:

```text
COLOR_BLOCK_CONFIRMATION_REQUIRED
```

This prevents an LLM plan from bypassing operator approval.

## Workflow File

`workflows/default.yaml` documents the expected task steps for developers and runtime tooling:

```text
record_context
check_robot
check_arm_gripper
human_confirmation
prepare_arm_pose
center_color_block
detect_color_block
capture_evidence
pick_color_block
reset_arm_home_holding_gripper
post_pick_gripper_state
capture_post_pick_evidence
post_pick_verify
capture_post_pick_stability_evidence
post_pick_stability_verify
place_color_block
remember_result
write_result
report_result
```

The YAML file does not replace code-level checks. The safety boundary remains Runtime permissions, resource locks, safety guards, and audit logs.

## Verification Commands

After using or changing this app, run:

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
```

These checks confirm that the app stays inside the Runtime boundary and does not depend on ROS2 directly.
