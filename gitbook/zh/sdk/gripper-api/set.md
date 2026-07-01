# ctx.gripper.set

`set`: 发送受控夹爪命令。

```python
async def set(
    command: str,
    force: str = "low",
    percentage: float | None = None,
    timeout_s: int = 5,
) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `command` | `str` | required | 夹爪命令，例如 `"open"` 或 `"close_gripper_low_force"`。 |
| `force` | `str` | `"low"` | 夹爪力度标签。 |
| `percentage` | `float \| None` | `None` | 可选开合百分比。 |
| `timeout_s` | `int` | `5` | 等待命令完成的超时时间。 |

## Returns

`SkillResult`

## Example

```python
await ctx.gripper.set("open", timeout_s=5)
```
