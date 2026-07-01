# ctx.report.say

`say` 向用户或运行日志报告消息。

## Signature

```python
async def say(message: str) -> SkillResult
```

## Parameters

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `message` | `str` | 报告内容 |

## Returns

`SkillResult`

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `report.say` |
| 权限 | `report.say` |
| Backend | Runtime internal report sink |
| Timeout | `3s` |

## Common Errors

- `PERMISSION_DENIED`
- `REPORT_BACKEND_UNAVAILABLE`
- `SKILL_BACKEND_UNAVAILABLE`

## Example

```python
await ctx.report.say("厨房检查完成，未发现异常。")
```
