# ctx.kernel.context

`ctx.kernel.context` 发送 context system calls，用于保存、读取、恢复和压缩当前 session 的上下文状态。

所有方法返回 `KernelSDKResult`。

## ctx.kernel.context.put

`put`: 写入一个 context key。

```python
async def put(key: str, value, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_put")`

Parameters:

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `key` | `str` | required | Context key。 |
| `value` | `Any` | required | 要保存的值。 |
| `ttl_s` | `int` | optional | 可选 TTL。 |
| `timeout_s` | `float` | optional | Kernel call timeout。 |

## ctx.kernel.context.get

`get`: 读取一个 context key。

```python
async def get(key: str, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_get")`

Parameters: `key`, optional `timeout_s`

## ctx.kernel.context.delete

`delete`: 删除一个 context key。

```python
async def delete(key: str, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_delete")`

Parameters: `key`, optional `timeout_s`

## ctx.kernel.context.list

`list`: 按 prefix 列出 context keys。

```python
async def list(prefix: str = "", limit: int = 100, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_list")`

Parameters: `prefix`, `limit`, optional `timeout_s`

## ctx.kernel.context.snapshot

`snapshot`: 保存 context checkpoint。

```python
async def snapshot(state: dict | None = None, checkpoint: str = "default", **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_snapshot")`

Parameters: `state`, `checkpoint`, optional `namespace`, `session_id`, `timeout_s`

## ctx.kernel.context.recover

`recover`: 从 checkpoint 恢复 context。

```python
async def recover(session_id: str = "", checkpoint: str = "", **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_recover")`

Parameters: `session_id`, `checkpoint`, optional `namespace`, `timeout_s`

## ctx.kernel.context.compact

`compact`: 压缩 context。

```python
async def compact(max_tokens: int = 2000, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_compact")`

Parameters: `max_tokens`, optional `namespace`, `session_id`, `timeout_s`

## ctx.kernel.context.clear

`clear`: 清理 context。

```python
async def clear(scope: str = "session", **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_clear")`

Parameters: `scope`, optional `namespace`, `session_id`, `timeout_s`

## Example

```python
result = await ctx.kernel.context.put("phase", "started", timeout_s=5)
if not result.success:
    return {"success": False, "error_code": result.error_code}
```
