# ctx.kernel.memory

Kernel memory API 提供更通用的记忆增删查改能力。普通应用的键值记忆优先使用 `ctx.memory.*`。

## Methods

```python
await ctx.kernel.memory.remember(content, key: str = "", **metadata)
await ctx.kernel.memory.add(content, key: str = "", **metadata)
await ctx.kernel.memory.search(query: str, limit: int = 5, **filters)
await ctx.kernel.memory.get(key: str, **kwargs)
await ctx.kernel.memory.update(key: str, content, **metadata)
await ctx.kernel.memory.delete(key: str, **kwargs)
await ctx.kernel.memory.list(limit: int = 100, **kwargs)
await ctx.kernel.memory.export(path: str, **kwargs)
await ctx.kernel.memory.import_(path: str, **kwargs)
```

## Returns

`KernelSDKResult`

## Example

```python
await ctx.kernel.memory.add({"summary": "inspection completed"}, key="last_inspection")
```
