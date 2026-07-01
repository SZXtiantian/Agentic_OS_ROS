# ctx.storage.list_recent_photos

`list_recent_photos`: 读取最近照片 evidence 记录。

```python
async def list_recent_photos(limit: int = 5) -> list[dict]
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `limit` | `int` | `5` | 返回数量，范围 `1..20`。 |

## Returns

`list[dict]`

每个元素是 Runtime 记录的照片 evidence metadata。

## Example

```python
photos = await ctx.storage.list_recent_photos(limit=3)
```
