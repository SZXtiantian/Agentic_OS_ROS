# ctx.kernel.memory

`ctx.kernel.memory` sends memory system calls for general memory write, search, read, update, delete, import, and export operations. Ordinary app key-value memory should use `ctx.memory.*` first.

All methods return `KernelSDKResult`.

| API | System Call |
| --- | --- |
| `remember(content, key="", **metadata)` | `MemoryQuery(operation_type="mem_remember")` |
| `add(content, key="", **metadata)` | `MemoryQuery(operation_type="mem_remember")` |
| `search(query, limit=5, **filters)` | `MemoryQuery(operation_type="mem_search")` |
| `get(key, **kwargs)` | `MemoryQuery(operation_type="mem_get")` |
| `update(key, content, **metadata)` | `MemoryQuery(operation_type="mem_update")` |
| `delete(key, **kwargs)` | `MemoryQuery(operation_type="mem_delete")` |
| `list(limit=100, **kwargs)` | `MemoryQuery(operation_type="mem_list")` |
| `export(path, **kwargs)` | `MemoryQuery(operation_type="mem_export")` |
| `import_(path, **kwargs)` | `MemoryQuery(operation_type="mem_import")` |

## Signatures

```python
async def remember(content, key: str = "", **metadata) -> KernelSDKResult
async def add(content, key: str = "", **metadata) -> KernelSDKResult
async def search(query: str, limit: int = 5, **filters) -> KernelSDKResult
async def get(key: str, **kwargs) -> KernelSDKResult
async def update(key: str, content, **metadata) -> KernelSDKResult
async def delete(key: str, **kwargs) -> KernelSDKResult
async def list(limit: int = 100, **kwargs) -> KernelSDKResult
async def export(path: str, **kwargs) -> KernelSDKResult
async def import_(path: str, **kwargs) -> KernelSDKResult
```

## Parameters

| Parameter | Description |
| --- | --- |
| `content` | Content to store or update. |
| `key` | Memory key; mapped to `memory_id` in the system call payload. |
| `query` | Search text. |
| `limit` | Maximum number of results. |
| `path` | Import or export path. |
| `metadata` / `filters` / `kwargs` | Optional metadata, filters, and `timeout_s`. |

## Example

```python
result = await ctx.kernel.memory.search("inspection", limit=5, timeout_s=5)
if result.success:
    matches = result.response.data.get("matches", [])
```
