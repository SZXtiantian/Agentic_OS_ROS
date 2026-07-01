# Robot API

`ctx.robot` provides robot mobility operations for Agent Apps. It is the SDK surface for reading robot state, navigating by place name, inspecting an area, and stopping robot motion.

Agent Apps must not publish `/cmd_vel` or call Nav2 actions directly.

## APIs

| API | Description |
| --- | --- |
| [`ctx.robot.get_state()`](get_state.md) | Read the current robot state. |
| [`ctx.robot.navigate_to(place, timeout_s=120)`](navigate_to.md) | Navigate to a named place. |
| [`ctx.robot.inspect_area(place, timeout_s=60)`](inspect_area.md) | Inspect a named area. |
| [`ctx.robot.stop(reason="app_requested")`](stop.md) | Request a controlled stop. |
