# ctx.kernel.memory

`ctx.kernel.memory` 发送 memory system calls，用于通用记忆写入、搜索、读取、更新、删除、导入和导出。普通 App 键值记忆优先使用 `ctx.memory.*`。

所有方法返回 `KernelSDKResult`。

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

| 参数 | 说明 |
| --- | --- |
| `content` | 要保存或更新的内容。 |
| `key` | 记忆 key；在 system call payload 中映射为 `memory_id`。 |
| `query` | 搜索文本。 |
| `limit` | 返回数量上限。 |
| `path` | 导入或导出路径。 |
| `metadata` / `filters` / `kwargs` | 可选 metadata、过滤条件和 `timeout_s`。 |

## Example

```python
result = await ctx.kernel.memory.search("inspection", limit=5, timeout_s=5)
if result.success:
    matches = result.response.data.get("matches", [])
```
