# ctx.report.log

`log` is a convenience wrapper around `report.say`. It formats messages as `[level] message`.

## Signature

```python
async def log(message: str, level: str = "info") -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `message` | `str` | required | Log message |
| `level` | `str` | `"info"` | Log level |

## Returns

`SkillResult`

## Example

```python
await ctx.report.log("inspection completed", level="info")
```
