# ctx.report.log

`log` 是 `report.say` 的便利封装，会把消息格式化为 `[level] message`。

## Signature

```python
async def log(message: str, level: str = "info") -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `message` | `str` | required | 日志内容 |
| `level` | `str` | `"info"` | 日志级别 |

## Returns

`SkillResult`

## Example

```python
await ctx.report.log("inspection completed", level="info")
```
