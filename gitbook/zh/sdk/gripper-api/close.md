# ctx.gripper.close

`close`: 关闭夹爪。

```python
async def close(force: str = "low", timeout_s: int = 5) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `force` | `str` | `"low"` | 夹爪力度。默认低力度。 |
| `timeout_s` | `int` | `5` | 等待命令完成的超时时间。 |

## Returns

`SkillResult`

## Example

```python
await ctx.gripper.close(force="low", timeout_s=5)
```
