# ctx.robot.get_state

`get_state`: Read the current robot state.

```python
async def get_state() -> RobotState
```

## Parameters

None.

## Returns

`RobotState`

```python
RobotState(
    robot_id: str,
    current_place: str,
    battery_percent: float,
    battery_state: str,
    is_moving: bool,
    active_task_id: str,
    mode: str,
    pose: dict,
    is_localized: bool,
    estop_pressed: bool,
    state: dict,
)
```

## Example

```python
state = await ctx.robot.get_state()
if state.estop_pressed:
    await ctx.report.say("Robot estop is pressed.")
```
