# ctx.memory.recall

`recall`: Read app memory by key.

```python
async def recall(key: str, default=None) -> Any
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `key` | `str` | required | Memory key to read. |
| `default` | `Any` | `None` | Value returned when the stored value is missing or `None`. |

## Returns

The stored value. If the value is missing or `None`, returns `default`.

## Example

```python
last = await ctx.memory.recall("last_inspection", default={})
```
