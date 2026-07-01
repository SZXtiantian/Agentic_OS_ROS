# Robot API

`ctx.robot` is the stable foundation interface for ordinary Agent Apps. It reads robot state, requests navigation, runs area inspection, and stops robot tasks.

| API | Skill | Permission | Return |
| --- | --- | --- | --- |
| [`ctx.robot.get_state()`](get_state.md) | `robot.get_state` | `robot.state.read` | `RobotState` |
| [`ctx.robot.navigate_to(place, timeout_s=120)`](navigate_to.md) | `robot.navigate_to` | `robot.move` | `SkillResult` |
| [`ctx.robot.inspect_area(place, timeout_s=60)`](inspect_area.md) | `robot.inspect_area` | `perception.inspect` | `InspectionResult` |
| [`ctx.robot.stop(reason="app_requested")`](stop.md) | `robot.stop` | `robot.stop` | `SkillResult` |

## Safety Rules

- Apps provide high-level targets such as place names.
- Apps must not publish velocity commands, send Nav2 goals, or call MoveIt.
- Navigation, inspection, and stop requests pass through Runtime permission, safety, resource-lock, and audit chains.
