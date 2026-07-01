# ctx.arm.get_state

`get_state`: Read the current arm state.

```python
async def get_state() -> ArmState
```

## Parameters

None.

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
