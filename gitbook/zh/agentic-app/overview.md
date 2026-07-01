# 如何使用 Agent App

Agent App 是运行在 Agentic Runtime 之上的任务编排代码。它负责理解用户任务、组织高层能力调用、保存结果和报告状态；它不是 ROS2 package，不是 bridge node，也不是硬件驱动。

本页用仓库里的示例 App 说明如何使用：

```text
agentic_apps/color_block_grasper_agent/
```

这个 App 的目标是：根据自然语言任务，选择指定颜色的积木，经过确认后调用受控的感知、机械臂、夹爪和放置能力完成任务。

## 使用入口

App 的入口在 `app.yaml`：

```yaml
name: color_block_grasper_agent
entrypoint: main:run
```

Runtime 启动 App 时会注入 `AgentContext`，然后调用 `main.py` 里的 `run(ctx, **kwargs)`。用户侧需要提供自然语言任务，例如：

```python
result = await run(ctx, task_text="夹起红色方块")
```

也可以使用 `message` 或 `text` 字段。三者都没有时，App 会返回结构化错误：

```json
{
  "success": false,
  "error_code": "COLOR_BLOCK_LLM_PLAN_REQUIRED"
}
```

## 运行流程

`color_block_grasper_agent` 的执行不是让 LLM 直接控制机器人。LLM 只负责把用户自然语言转换成一个 JSON plan；真正执行前，App 会用确定性代码校验计划和权限。

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

LLM plan 必须包含固定字段：`schema_version`、`planner_mode`、`target_color`、`place_target`、`requires_manipulation`、`needs_confirmation`、`steps`、`risk_class`、`user_summary`。

`target_color` 必须来自 App manifest 和 system skill contract 声明的颜色 allowlist；本教程统一使用 `red`。`steps` 必须严格等于 App 规定的确定性序列：

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

如果 LLM 少字段、颜色不允许、步骤顺序不对，App 会返回 `COLOR_BLOCK_LLM_PLAN_INVALID`，不会继续调用机器人能力。

## 用户会看到什么结果

成功结果会包含：

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

失败结果也必须是结构化的，包含 `error_code`、`reason`、`missing`、`next_action` 和已执行的 `steps`。这对调试真实机器人依赖很重要，例如 perception bridge 未启动时，App 不会伪造成功，而是返回 capability 或 backend 不可用的错误。

## App 使用的能力

`app.yaml` 里声明了 App 允许调用的权限和能力。这个示例使用：

| 分类 | 能力 |
| --- | --- |
| LLM | `ctx.llm.chat_json(...)` |
| Robot | `robot.get_state`、`robot.stop` |
| Human | `human.ask` |
| Perception | `perception.center_color_block`、`perception.detect_color_block`、`perception.capture_photo`、`perception.verify_held_color_block` |
| Arm | `arm.get_state`、`arm.move_named` |
| Gripper | `gripper.set` readiness/holding checks |
| Manipulation | `manipulation.pick_color_block`、`manipulation.place_color_block` |
| Runtime state | `ctx.kernel.context.*`、`ctx.kernel.memory.*`、`ctx.kernel.storage.*` |
| Report | `report.say` |

机器人运动、感知和机械臂动作都通过 `ctx.kernel.skill.call(...)` 调 system skill。App 不导入 `rclpy`，不发布 `/cmd_vel`，不直接调用 Nav2 或 MoveIt。

## 人工确认

真实抓取和放置属于高风险动作。示例 App 在执行前会调用：

```python
await ctx.kernel.skill.call("human.ask", {...})
```

问题会要求操作员明确回答 `CONFIRM`。未确认时返回：

```text
COLOR_BLOCK_CONFIRMATION_REQUIRED
```

这样可以保证 LLM plan 不能绕过人工确认。

## 工作流文件

`workflows/default.yaml` 是给开发者和运行时工具阅读的任务步骤清单，当前包含：

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

这份 YAML 不替代代码校验。真正的安全边界仍然在 Runtime 权限、资源锁、安全守卫和 audit log 中。

## 验证命令

使用或修改这个 App 后，至少运行：

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/color_block_grasper_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/color_block_grasper_agent/tests
```

这些检查会确认 App 没有越过 Runtime 边界，也没有直接依赖 ROS2。
