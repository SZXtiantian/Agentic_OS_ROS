# ctx.report.log

`log`: 带级别前缀报告一条消息。

```python
async def log(message: str, level: str = "info") -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `message` | `str` | required | 要报告的消息。 |
| `level` | `str` | `"info"` | 消息级别，会作为前缀写入报告消息。 |

## Returns

`SkillResult`

## Example

```python
await ctx.report.log("开始检查厨房", level="info")
```
