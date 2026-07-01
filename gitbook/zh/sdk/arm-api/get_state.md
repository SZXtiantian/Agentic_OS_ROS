# ctx.arm.get_state

读取机械臂 readiness、active action、运动状态和夹爪 readiness。

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

| 项 | 值 |
| --- | --- |
| Skill | `arm.get_state` |
| 权限 | `arm.state.read` |
| 后端 | ROS2 service `/agentic/arm/get_state` |
| Timeout | `5s` |

## Example

```python
arm_state = await ctx.arm.get_state()
```
