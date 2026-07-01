# ctx.gripper.close

`close`: Close the gripper.

```python
async def close(force: str = "low", timeout_s: int = 5) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `force` | `str` | `"low"` | Gripper force label. Defaults to low force. |
| `timeout_s` | `int` | `5` | Timeout for waiting for the command to complete. |

## Returns

`SkillResult`

## Example

```python
await ctx.gripper.close(force="low", timeout_s=5)
```
