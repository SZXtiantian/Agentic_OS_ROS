# ctx.report.say

`say`: 报告一条任务进度或结果消息。

```python
async def say(message: str) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `message` | `str` | required | 要报告的消息。 |

## Returns

`SkillResult`

## Example

```python
await ctx.report.say("检查完成。")
```
