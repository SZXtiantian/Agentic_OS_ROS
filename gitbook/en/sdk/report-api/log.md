# ctx.report.log

`log`: Report a message with a level prefix.

```python
async def log(message: str, level: str = "info") -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `message` | `str` | required | Message to report. |
| `level` | `str` | `"info"` | Message level added as a prefix. |

## Returns

`SkillResult`

## Example

```python
await ctx.report.log("Starting kitchen inspection", level="info")
```
