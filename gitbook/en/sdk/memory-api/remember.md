# ctx.memory.remember

`remember`: Store a piece of app data under a key.

```python
async def remember(key: str, value: Any) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `key` | `str` | required | Memory key. |
| `value` | `Any` | required | Value to store, usually compact JSON-compatible data. |

## Returns

`SkillResult`

## Example

```python
await ctx.memory.remember("last_inspection", {"place": "kitchen", "ok": True})
```
