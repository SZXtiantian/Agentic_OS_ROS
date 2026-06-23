# API v0.1

Foundation Agent Apps may call only high-level Agentic APIs:

- `ctx.robot.get_state()`
- `ctx.robot.navigate_to(place)`
- `ctx.robot.inspect_area(place)`
- `ctx.robot.stop()`
- `ctx.world.resolve_place(name)`
- `ctx.memory.remember(key, value)`
- `ctx.memory.recall(key)`
- `ctx.human.ask(question)`
- `ctx.report.say(message)`

Agent Apps must not import `rclpy`, publish `/cmd_vel`, directly subscribe to `/scan`, `/odom`, or `/tf`, or directly call Nav2 / MoveIt actions.

## Result Model

All Runtime skill calls return or raise structured results with:

- `success`
- `error_code`
- `reason`
- `recoverable`
- `suggested_recovery`
- `audit_id`

Failure codes include `PLACE_NOT_FOUND`, `FORBIDDEN_ZONE`, `PERMISSION_DENIED`, `RESOURCE_LOCKED`, `SAFETY_REJECTED`, `SKILL_TIMEOUT`, `SKILL_CANCELLED`, `NAVIGATION_TIMEOUT`, `BACKEND_UNAVAILABLE`, and `UNEXPECTED_ERROR`.

## Demo Flow

For “去厨房看看” the foundation app executes:

1. `ctx.world.resolve_place("厨房")`
2. `ctx.robot.get_state()`
3. `ctx.robot.navigate_to("厨房")`
4. `ctx.robot.inspect_area("厨房")`
5. `ctx.memory.remember("last_inspection", result)`
6. `ctx.report.say("厨房检查完成，未发现异常。")`
