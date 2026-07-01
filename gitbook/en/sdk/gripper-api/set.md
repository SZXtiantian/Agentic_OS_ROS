# ctx.gripper.set

`set`: Send a controlled gripper command.

```python
async def set(
    command: str,
    force: str = "low",
    percentage: float | None = None,
    timeout_s: int = 5,
) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `command` | `str` | required | Gripper command, such as `"open"` or `"close_gripper_low_force"`. |
| `force` | `str` | `"low"` | Gripper force label. |
| `percentage` | `float \| None` | `None` | Optional open/close percentage. |
| `timeout_s` | `int` | `5` | Timeout for waiting for the command to complete. |

## Returns

`SkillResult`

## Example

```python
await ctx.gripper.set("open", timeout_s=5)
```
