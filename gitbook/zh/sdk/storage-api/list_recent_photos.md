# ctx.storage.list_recent_photos

读取 Runtime 管理的照片 evidence 索引。

## Signature

```python
async def list_recent_photos(limit: int = 5) -> list[dict]
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `limit` | `int` | `5` | 返回数量，范围 `1..20` |

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `storage.list_recent_photos` |
| 权限 | `storage.read` |
| 后端 | Runtime internal storage index |
| Timeout | `5s` |

## Example

```python
photos = await ctx.storage.list_recent_photos(limit=3)
```
