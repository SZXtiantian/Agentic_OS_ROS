# ctx.arm.get_state

Read arm readiness, active action, motion state, and gripper readiness.

## Signature

```python
async def get_state() -> ArmState
```

## Returns

`ArmState`

```python
readiness: str
active_action: str
is_moving: bool
gripper_ready: bool
stop_available: bool
state: dict
```

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `arm.get_state` |
| Permission | `arm.state.read` |
| Backend | ROS2 service `/agentic/arm/get_state` |
| Timeout | `5s` |

## Example

```python
arm_state = await ctx.arm.get_state()
```
