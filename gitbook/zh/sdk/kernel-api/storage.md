# ctx.kernel.storage

Kernel storage API 管理 Runtime storage 中的文件、版本、索引和检索。高风险操作可能触发 access/intervention。

## Methods

```python
await ctx.kernel.storage.mount(collection_name: str = "default", **kwargs)
await ctx.kernel.storage.mkdir(path: str, **kwargs)
await ctx.kernel.storage.create_file(path: str, **kwargs)
await ctx.kernel.storage.write(path: str, content, **metadata)
await ctx.kernel.storage.read(path: str, **kwargs)
await ctx.kernel.storage.list(path: str = ".", **kwargs)
await ctx.kernel.storage.delete(path: str, **kwargs)
await ctx.kernel.storage.stat(path: str, **kwargs)
await ctx.kernel.storage.history(path: str, **kwargs)
await ctx.kernel.storage.rollback(path: str, version: str = "", **kwargs)
await ctx.kernel.storage.share(path: str, **metadata)
await ctx.kernel.storage.index(collection_name: str = "", **kwargs)
await ctx.kernel.storage.retrieve(query: str, collection_name: str = "", limit: int = 5)
```

## Returns

`KernelSDKResult`

## Example

```python
await ctx.kernel.storage.write("reports/inspection.json", {"success": True})
```
