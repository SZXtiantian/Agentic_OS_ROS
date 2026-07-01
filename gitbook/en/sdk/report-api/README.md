# Report API

`ctx.report` writes user-facing or runtime report messages.

## APIs

| API | Skill | Permission | Return |
| --- | --- | --- | --- |
| `ctx.report.say(message)` | `report.say` | `report.say` | `SkillResult` |
| `ctx.report.log(message, level="info")` | wraps `report.say` | `report.say` | `SkillResult` |

## ctx.report.say

```python
async def say(message: str) -> SkillResult
```

The report sink writes to `AGENTIC_REPORT_LOG` or `$AGENTIC_VAR/reports/report.jsonl`. Installed systems usually use `/opt/agentic/var/reports/report.jsonl`.

Example:

```python
await ctx.report.say("Kitchen inspection completed. No anomalies found.")
```

## ctx.report.log

```python
async def log(message: str, level: str = "info") -> SkillResult
```

`log()` formats the message as `[level] message` and delegates to `say()`.

Common errors:

- `PERMISSION_DENIED`
- `REPORT_BACKEND_UNAVAILABLE`
- `SKILL_BACKEND_UNAVAILABLE`
