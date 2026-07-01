# ctx.kernel.context

Kernel context API 用于保存、恢复和压缩当前 session 的上下文状态。

## Methods

```python
await ctx.kernel.context.snapshot(state: dict | None = None, checkpoint: str = "default", **kwargs)
await ctx.kernel.context.recover(session_id: str = "", checkpoint: str = "", **kwargs)
await ctx.kernel.context.put(key: str, value, **kwargs)
await ctx.kernel.context.get(key: str, **kwargs)
await ctx.kernel.context.delete(key: str, **kwargs)
await ctx.kernel.context.list(prefix: str = "", limit: int = 100, **kwargs)
await ctx.kernel.context.compact(max_tokens: int = 2000, **kwargs)
await ctx.kernel.context.clear(scope: str = "session", **kwargs)
```

## Returns

`KernelSDKResult`

## Example

```python
result = await ctx.kernel.context.put("phase", "started")
if not result.success:
    return {"success": False, "error_code": result.error_code}
```
