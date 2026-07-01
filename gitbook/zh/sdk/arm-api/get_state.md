# ctx.arm.get_state

`get_state`: 读取当前机械臂状态。

```python
async def get_state() -> ArmState
```

## Parameters

无。

## Returns

`ArmState`

```python
ArmState(
    readiness: str,
    active_action: str,
    is_moving: bool,
    gripper_ready: bool,
    stop_available: bool,
    state: dict,
)
```

## Example

```python
arm = await ctx.arm.get_state()
if arm.is_moving:
    await ctx.report.say("Arm is moving.")
```
