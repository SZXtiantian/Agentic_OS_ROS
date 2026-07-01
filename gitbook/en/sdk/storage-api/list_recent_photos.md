# ctx.storage.list_recent_photos

Read the Runtime-managed photo evidence index.

## Signature

```python
async def list_recent_photos(limit: int = 5) -> list[dict]
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `limit` | `int` | `5` | Number of entries, range `1..20` |

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `storage.list_recent_photos` |
| Permission | `storage.read` |
| Backend | Runtime internal storage index |
| Timeout | `5s` |

## Example

```python
photos = await ctx.storage.list_recent_photos(limit=3)
```
