# ctx.gripper.close

Close the gripper. `force="low"` maps to the allowlisted command `"close_gripper_low_force"`.

## Signature

```python
async def close(force: str = "low", timeout_s: int = 5) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `force` | `str` | `"low"` | Force policy |
| `timeout_s` | `int` | `5` | Timeout |

## Example

```python
await ctx.gripper.close(force="low")
```
