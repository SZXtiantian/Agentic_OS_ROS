# ctx.gripper.open

`open`: 打开夹爪。

```python
async def open(timeout_s: int = 5) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout_s` | `int` | `5` | 等待命令完成的超时时间。 |

## Returns

`SkillResult`

## Example

```python
await ctx.gripper.open(timeout_s=5)
```
