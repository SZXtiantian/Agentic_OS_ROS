# ctx.memory.recall

`recall`: 按 key 读取 App 记忆。

```python
async def recall(key: str, default=None) -> Any
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `key` | `str` | required | 要读取的记忆 key。 |
| `default` | `Any` | `None` | 当值缺失或为 `None` 时返回的默认值。 |

## Returns

保存的值；如果值缺失或为 `None`，返回 `default`。

## Example

```python
last = await ctx.memory.recall("last_inspection", default={})
```
