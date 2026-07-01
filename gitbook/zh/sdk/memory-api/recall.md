# ctx.memory.recall

`recall` 读取应用级记忆。缺失或 value 为 `None` 时返回 `default`。

## Signature

```python
async def recall(key: str, default: Any = None) -> Any
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `key` | `str` | required | 记忆键 |
| `default` | `Any` | `None` | 缺失时返回的默认值 |

## Returns

存储值或 `default`。

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `memory.recall` |
| 权限 | `memory.read` |
| 后端 | Runtime internal memory store，默认 SQLite |
| Timeout | `3s` |

## Common Errors

- `PERMISSION_DENIED`
- `MEMORY_PROVIDER_UNAVAILABLE`
- `MEMORY_BACKEND_UNAVAILABLE`
- `MEMORY_RESULT_INVALID`

## Example

```python
last = await ctx.memory.recall("last_inspection", default={})
```
