# Memory API

`ctx.memory` provides app-level key-value memory for task summaries, previous inspection results, and user preferences. Do not store secrets, raw images, videos, or unaudited private data.

## APIs

| API | Skill | Permission | Return |
| --- | --- | --- | --- |
| `ctx.memory.remember(key, value)` | `memory.remember` | `memory.write` | `SkillResult` |
| `ctx.memory.recall(key, default=None)` | `memory.recall` | `memory.read` | `Any` |

## ctx.memory.remember

```python
async def remember(key: str, value: Any) -> SkillResult
```

Runtime contract:

| Item | Value |
| --- | --- |
| Backend | Runtime internal memory store, SQLite by default |
| Resource lock | None |
| Timeout | `3s` |

Example:

```python
await ctx.memory.remember("last_requested_place", "kitchen")
```

## ctx.memory.recall

```python
async def recall(key: str, default: Any = None) -> Any
```

Returns `default` when the stored value is missing or `None`.

Example:

```python
last = await ctx.memory.recall("last_inspection", default={})
```

Common errors:

- `PERMISSION_DENIED`
- `MEMORY_PROVIDER_UNAVAILABLE`
- `MEMORY_BACKEND_UNAVAILABLE`
- `MEMORY_RESULT_INVALID`
- `SCHEMA_INVALID`
