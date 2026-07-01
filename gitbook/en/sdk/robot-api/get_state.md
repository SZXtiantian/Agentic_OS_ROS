# ctx.robot.get_state

Read the current robot state.

## Signature

```python
async def get_state() -> RobotState
```

## Parameters

None.

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

| Item | Value |
| --- | --- |
| Skill | `robot.get_state` |
| Permission | `robot.state.read` |
| Backend | ROS2 service `/agentic/robot/get_state` |
| Resource lock | None |
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
