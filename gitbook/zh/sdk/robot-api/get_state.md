# ctx.robot.get_state

读取机器人当前状态。

## Signature

```python
async def get_state() -> RobotState
```

## Parameters

无。

## Returns

`RobotState`

```python
robot_id: str
mode: str
battery_state: str
battery_percent: float
is_localized: bool
is_moving: bool
estop_pressed: bool
current_place: str
pose: dict[str, float]
active_task_id: str
state: dict
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `robot.get_state` |
| 权限 | `robot.state.read` |
| 后端 | ROS2 service `/agentic/robot/get_state` |
| 资源锁 | 无 |
| Timeout | `10s` |

## Common Errors

- `PERMISSION_DENIED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
- `UNEXPECTED_ERROR`

## Example

```python
state = await ctx.robot.get_state()
if state.estop_pressed:
    return {"success": False, "error_code": "ESTOP_PRESSED", "reason": "robot estop is pressed"}
```
