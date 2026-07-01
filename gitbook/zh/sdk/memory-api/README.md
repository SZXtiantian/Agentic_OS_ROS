# Memory API

`ctx.memory` 提供应用级键值记忆。适合保存任务摘要、上次检查结果、用户偏好等；不要保存密钥、原始大图、视频或不可审计的隐私数据。

## APIs

| API | Skill | 权限 | 返回 |
| --- | --- | --- | --- |
| `ctx.memory.remember(key, value)` | `memory.remember` | `memory.write` | `SkillResult` |
| `ctx.memory.recall(key, default=None)` | `memory.recall` | `memory.read` | `Any` |

## ctx.memory.remember

```python
async def remember(key: str, value: Any) -> SkillResult
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| 后端 | Runtime internal memory store，默认 SQLite |
| 资源锁 | 无 |
| Timeout | `3s` |

示例：

```python
await ctx.memory.remember("last_requested_place", "厨房")
```

## ctx.memory.recall

```python
async def recall(key: str, default: Any = None) -> Any
```

缺失或 value 为 `None` 时返回 `default`。

示例：

```python
last = await ctx.memory.recall("last_inspection", default={})
```

常见错误：

- `PERMISSION_DENIED`
- `MEMORY_PROVIDER_UNAVAILABLE`
- `MEMORY_BACKEND_UNAVAILABLE`
- `MEMORY_RESULT_INVALID`
- `SCHEMA_INVALID`
