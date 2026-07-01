# ctx.report.say

`say` reports a message to the user or runtime log sink.

## Signature

```python
async def say(message: str) -> SkillResult
```

## Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `message` | `str` | Report message |

## Returns

`SkillResult`

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `report.say` |
| Permission | `report.say` |
| Backend | Runtime internal report sink |
| Timeout | `3s` |

## Common Errors

- `PERMISSION_DENIED`
- `REPORT_BACKEND_UNAVAILABLE`
- `SKILL_BACKEND_UNAVAILABLE`

## Example

```python
await ctx.report.say("Kitchen inspection completed. No anomalies found.")
```
