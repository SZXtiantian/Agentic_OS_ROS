# ctx.kernel.storage

`ctx.kernel.storage` 发送 storage system calls，用于直接操作 Runtime-managed storage 中的 collection、文件、版本、索引和检索。

这不是 `ctx.storage` 高层 evidence SDK。`ctx.kernel.storage.*` 返回 `KernelSDKResult`，并进入 Kernel system call 路径。

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

| 参数 | 说明 |
| --- | --- |
| `collection_name` | Runtime storage collection 名称。 |
| `path` | Runtime storage 内的相对路径。不能是绝对路径，不能越过 storage root。 |
| `content` | 写入内容。dict/list 会被写成 JSON 文本。 |
| `metadata` | 写入、分享或索引时附带的 metadata。 |
| `version` | rollback 使用的版本名；为空时使用最近版本。 |
| `query` | 检索文本。 |
| `limit` | 检索结果数量上限。 |
| `timeout_s` | 可选 Kernel call timeout；通过 `kwargs` 或 `metadata` 传入。 |

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
