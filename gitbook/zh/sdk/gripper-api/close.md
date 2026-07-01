# ctx.gripper.close

关闭夹爪。`force="low"` 会映射为 allowlist 命令 `"close_gripper_low_force"`。

## Signature

```python
async def close(force: str = "low", timeout_s: int = 5) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `force` | `str` | `"low"` | 夹爪力度策略 |
| `timeout_s` | `int` | `5` | 超时时间 |

## Example

```python
await ctx.gripper.close(force="low")
```
