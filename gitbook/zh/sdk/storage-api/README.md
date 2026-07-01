# Storage API

`ctx.storage` 当前提供 Runtime 管理的照片 evidence 索引读取。

## ctx.storage.list_recent_photos

```python
async def list_recent_photos(limit: int = 5) -> list[dict]
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `storage.list_recent_photos` |
| 权限 | `storage.read` |
| 后端 | Runtime internal storage index |
| Limit | `1..20` |
| Timeout | `5s` |

示例：

```python
photos = await ctx.storage.list_recent_photos(limit=3)
```
