# ctx.memory.remember

`remember` 写入应用级记忆。

## Signature

```python
async def remember(key: str, value: Any) -> SkillResult
```

## Parameters

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `key` | `str` | 记忆键 |
| `value` | `Any` | JSON-like 值 |

## Returns

`SkillResult`

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `memory.remember` |
| 权限 | `memory.write` |
| 后端 | Runtime internal memory store，默认 SQLite |
| Timeout | `3s` |

## Common Errors

- `PERMISSION_DENIED`
- `MEMORY_PROVIDER_UNAVAILABLE`
- `MEMORY_RESULT_INVALID`
- `SCHEMA_INVALID`

## Example

```python
await ctx.memory.remember("last_requested_place", "厨房")
```
