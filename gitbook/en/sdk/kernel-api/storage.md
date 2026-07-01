# ctx.kernel.storage

`ctx.kernel.storage` sends storage system calls for direct operations on Runtime-managed storage collections, files, versions, indexes, and retrieval.

This is not the high-level `ctx.storage` evidence SDK. `ctx.kernel.storage.*` returns `KernelSDKResult` and enters the Kernel system call path.

## APIs

| API | System Call |
| --- | --- |
| `mount(collection_name="default", **kwargs)` | `StorageQuery(operation_type="sto_mount")` |
| `mkdir(path, **kwargs)` | `StorageQuery(operation_type="sto_mkdir")` |
| `create_file(path, **kwargs)` | `StorageQuery(operation_type="sto_create_file")` |
| `write(path, content, **metadata)` | `StorageQuery(operation_type="sto_write")` |
| `read(path, **kwargs)` | `StorageQuery(operation_type="sto_read")` |
| `list(path=".", **kwargs)` | `StorageQuery(operation_type="sto_list")` |
| `delete(path, **kwargs)` | `StorageQuery(operation_type="sto_delete")` |
| `stat(path, **kwargs)` | `StorageQuery(operation_type="sto_stat")` |
| `history(path, **kwargs)` | `StorageQuery(operation_type="sto_history")` |
| `rollback(path, version="", **kwargs)` | `StorageQuery(operation_type="sto_rollback")` |
| `share(path, **metadata)` | `StorageQuery(operation_type="sto_share")` |
| `index(collection_name="", **kwargs)` | `StorageQuery(operation_type="sto_index")` |
| `retrieve(query, collection_name="", limit=5)` | `StorageQuery(operation_type="sto_retrieve")` |

## Signatures

```python
async def mount(collection_name: str = "default", **kwargs) -> KernelSDKResult
async def mkdir(path: str, **kwargs) -> KernelSDKResult
async def create_file(path: str, **kwargs) -> KernelSDKResult
async def write(path: str, content, **metadata) -> KernelSDKResult
async def read(path: str, **kwargs) -> KernelSDKResult
async def list(path: str = ".", **kwargs) -> KernelSDKResult
async def delete(path: str, **kwargs) -> KernelSDKResult
async def stat(path: str, **kwargs) -> KernelSDKResult
async def history(path: str, **kwargs) -> KernelSDKResult
async def rollback(path: str, version: str = "", **kwargs) -> KernelSDKResult
async def share(path: str, **metadata) -> KernelSDKResult
async def index(collection_name: str = "", **kwargs) -> KernelSDKResult
async def retrieve(query: str, collection_name: str = "", limit: int = 5) -> KernelSDKResult
```

## Parameters

| Parameter | Description |
| --- | --- |
| `collection_name` | Runtime storage collection name. |
| `path` | Relative path inside Runtime storage. It cannot be absolute and cannot escape the storage root. |
| `content` | Content to write. Dicts and lists are written as JSON text. |
| `metadata` | Metadata attached to write, share, or index operations. |
| `version` | Version name for rollback; empty string means latest version. |
| `query` | Retrieval text. |
| `limit` | Maximum number of retrieval results. |
| `timeout_s` | Optional Kernel call timeout passed through `kwargs` or `metadata`. |

## Returns

`KernelSDKResult`

## Example

```python
result = await ctx.kernel.storage.write(
    "reports/inspection.json",
    {"success": True},
    timeout_s=5,
)
if not result.success:
    return {"success": False, "error_code": result.error_code}
```
