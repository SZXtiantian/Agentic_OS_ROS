# ctx.storage.list_recent_photos

`list_recent_photos`: Read recent photo evidence records.

```python
async def list_recent_photos(limit: int = 5) -> list[dict]
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `limit` | `int` | `5` | Number of records to return, range `1..20`. |

## Returns

`list[dict]`

Each item is photo evidence metadata recorded by Runtime.

## Example

```python
photos = await ctx.storage.list_recent_photos(limit=3)
```
