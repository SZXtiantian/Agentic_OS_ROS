# ctx.gripper.open

`open`: Open the gripper.

```python
async def open(timeout_s: int = 5) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `timeout_s` | `int` | `5` | Timeout for waiting for the command to complete. |

## Returns

`SkillResult`

## Example

```python
await ctx.gripper.open(timeout_s=5)
```
