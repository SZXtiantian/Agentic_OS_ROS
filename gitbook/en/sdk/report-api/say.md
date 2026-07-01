# ctx.report.say

`say`: Report a task progress or result message.

```python
async def say(message: str) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `message` | `str` | required | Message to report. |

## Returns

`SkillResult`

## Example

```python
await ctx.report.say("Inspection completed.")
```
