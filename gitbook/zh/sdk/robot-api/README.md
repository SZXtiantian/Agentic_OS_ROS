# Robot API

`ctx.robot` 提供移动机器人相关操作。它是 Agent App 读取机器人状态、按地点导航、检查区域和请求停止的 SDK 入口。

Agent App 不直接发布 `/cmd_vel`，也不直接调用 Nav2 action。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.robot.get_state()`](get_state.md) | 读取当前机器人状态。 |
| [`ctx.robot.navigate_to(place, timeout_s=120)`](navigate_to.md) | 导航到一个地点名称。 |
| [`ctx.robot.inspect_area(place, timeout_s=60)`](inspect_area.md) | 检查一个地点或区域。 |
| [`ctx.robot.stop(reason="app_requested")`](stop.md) | 请求受控停止。 |
