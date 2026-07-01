# Report API

`ctx.report` 用于向用户或运行日志报告消息。

## APIs

| API | Skill | 权限 | 返回 |
| --- | --- | --- | --- |
| `ctx.report.say(message)` | `report.say` | `report.say` | `SkillResult` |
| `ctx.report.log(message, level="info")` | wraps `report.say` | `report.say` | `SkillResult` |

## ctx.report.say

```python
async def say(message: str) -> SkillResult
```

当前 report sink 会写入 `AGENTIC_REPORT_LOG` 或 `$AGENTIC_VAR/reports/report.jsonl`。安装后默认路径通常是 `/opt/agentic/var/reports/report.jsonl`。

示例：

```python
await ctx.report.say("厨房检查完成，未发现异常。")
```

## ctx.report.log

```python
async def log(message: str, level: str = "info") -> SkillResult
```

`log()` 会把消息格式化为 `[level] message` 后调用 `say()`。

常见错误：

- `PERMISSION_DENIED`
- `REPORT_BACKEND_UNAVAILABLE`
- `SKILL_BACKEND_UNAVAILABLE`
