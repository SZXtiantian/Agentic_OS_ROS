# ctx.kernel.context

`ctx.kernel.context` sends context system calls for storing, reading, recovering, and compacting session context state.

All methods return `KernelSDKResult`.

## ctx.kernel.context.put

`put`: Write a context key.

```python
async def put(key: str, value, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_put")`

Parameters:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `key` | `str` | required | Context key. |
| `value` | `Any` | required | Value to store. |
| `ttl_s` | `int` | optional | Optional TTL. |
| `timeout_s` | `float` | optional | Kernel call timeout. |

## ctx.kernel.context.get

`get`: Read a context key.

```python
async def get(key: str, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_get")`

Parameters: `key`, optional `timeout_s`

## ctx.kernel.context.delete

`delete`: Delete a context key.

```python
async def delete(key: str, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_delete")`

Parameters: `key`, optional `timeout_s`

## ctx.kernel.context.list

`list`: List context keys by prefix.

```python
async def list(prefix: str = "", limit: int = 100, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_list")`

Parameters: `prefix`, `limit`, optional `timeout_s`

## ctx.kernel.context.snapshot

`snapshot`: Save a context checkpoint.

```python
async def snapshot(state: dict | None = None, checkpoint: str = "default", **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_snapshot")`

Parameters: `state`, `checkpoint`, optional `namespace`, `session_id`, `timeout_s`

## ctx.kernel.context.recover

`recover`: Recover context from a checkpoint.

```python
async def recover(session_id: str = "", checkpoint: str = "", **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_recover")`

Parameters: `session_id`, `checkpoint`, optional `namespace`, `timeout_s`

## ctx.kernel.context.compact

`compact`: Compact context.

```python
async def compact(max_tokens: int = 2000, **kwargs) -> KernelSDKResult
```

System Call: `ContextQuery(operation_type="ctx_compact")`

Parameters: `max_tokens`, optional `namespace`, `session_id`, `timeout_s`

## ctx.kernel.context.clear

`clear`: Clear context.

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
