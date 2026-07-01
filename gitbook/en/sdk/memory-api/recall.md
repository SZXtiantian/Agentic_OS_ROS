# ctx.memory.recall

`recall` reads app-level memory. It returns `default` when the stored value is missing or `None`.

## Signature

```python
async def recall(key: str, default: Any = None) -> Any
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `key` | `str` | required | Memory key |
| `default` | `Any` | `None` | Value returned when missing |

## Returns

The stored value or `default`.

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `memory.recall` |
| Permission | `memory.read` |
| Backend | Runtime internal memory store, SQLite by default |
| Timeout | `3s` |

## Common Errors

- `PERMISSION_DENIED`
- `MEMORY_PROVIDER_UNAVAILABLE`
- `MEMORY_BACKEND_UNAVAILABLE`
- `MEMORY_RESULT_INVALID`

## Example

```python
last = await ctx.memory.recall("last_inspection", default={})
```
