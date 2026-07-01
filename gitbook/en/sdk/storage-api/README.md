# Storage API

`ctx.storage` currently reads Runtime-managed photo evidence indexes.

## ctx.storage.list_recent_photos

```python
async def list_recent_photos(limit: int = 5) -> list[dict]
```

Runtime contract:

| Item | Value |
| --- | --- |
| Skill | `storage.list_recent_photos` |
| Permission | `storage.read` |
| Backend | Runtime internal storage index |
| Limit | `1..20` |
| Timeout | `5s` |

Example:

```python
photos = await ctx.storage.list_recent_photos(limit=3)
```
