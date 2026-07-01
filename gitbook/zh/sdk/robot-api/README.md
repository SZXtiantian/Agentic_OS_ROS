# Robot API

`ctx.robot` 是普通 Agent App 最重要的稳定接口，用于读取机器人状态、请求导航、执行区域检查和停止机器人任务。

| API | Skill | 权限 | 返回 |
| --- | --- | --- | --- |
| [`ctx.robot.get_state()`](get_state.md) | `robot.get_state` | `robot.state.read` | `RobotState` |
| [`ctx.robot.navigate_to(place, timeout_s=120)`](navigate_to.md) | `robot.navigate_to` | `robot.move` | `SkillResult` |
| [`ctx.robot.inspect_area(place, timeout_s=60)`](inspect_area.md) | `robot.inspect_area` | `perception.inspect` | `InspectionResult` |
| [`ctx.robot.stop(reason="app_requested")`](stop.md) | `robot.stop` | `robot.stop` | `SkillResult` |

## 安全原则

- 应用只能给高层目标，例如地点名。
- 应用不能发布速度、直接发 Nav2 goal、直接调用 MoveIt。
- 导航、检查、停止都会进入 Runtime 的权限、安全、资源锁和审计链。
