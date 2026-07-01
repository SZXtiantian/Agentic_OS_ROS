# ctx.memory.remember

`remember` writes app-level memory.

## Signature

```python
async def remember(key: str, value: Any) -> SkillResult
```

## Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `key` | `str` | Memory key |
| `value` | `Any` | JSON-like value |

## Returns

`SkillResult`

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `memory.remember` |
| Permission | `memory.write` |
| Backend | Runtime internal memory store, SQLite by default |
| Timeout | `3s` |

## Common Errors

- `PERMISSION_DENIED`
- `MEMORY_PROVIDER_UNAVAILABLE`
- `MEMORY_RESULT_INVALID`
- `SCHEMA_INVALID`

## Example

```python
await ctx.memory.remember("last_requested_place", "kitchen")
```
