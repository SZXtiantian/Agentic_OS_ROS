# ctx.memory.remember

`remember`: 把一段 App 数据保存到指定 key。

```python
async def remember(key: str, value: Any) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `key` | `str` | required | 记忆 key。 |
| `value` | `Any` | required | 要保存的值，通常是小段 JSON-compatible 数据。 |

## Returns

`SkillResult`

## Example

```python
await ctx.memory.remember("last_inspection", {"place": "厨房", "ok": True})
```
