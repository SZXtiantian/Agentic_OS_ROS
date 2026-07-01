# Agentic System Calls

`ctx.kernel.*` is the Agentic System Call facade. It converts Python calls into Kernel system call operations that can be scheduled, audited, and executed by Runtime.

Ordinary Agent Apps should use Agentic SDK APIs first, such as `ctx.robot.*`, `ctx.memory.*`, and `ctx.report.*`. Use `ctx.kernel.*` when an app needs direct Kernel context, memory, storage, LLM, tool, or skill scheduling operations.

## Call Model

```text
ctx.kernel.storage.write(...)
  -> StorageQuery(operation_type="sto_write")
  -> Kernel scheduler / executor
  -> storage manager
  -> KernelSDKResult
```

## Result

Most `ctx.kernel.*` calls return:

```python
KernelSDKResult(
    success: bool,
    response: Any = None,
    error_code: str = "",
    syscall_id: str = "",
    audit_id: str = "",
    metadata: dict = {},
    raw: Any = None,
)
```

`ctx.kernel.access.*` is an access manager facade. It returns an access decision dict and does not enter the queued system call path.

## Namespaces

| Facade | System call operations |
| --- | --- |
| `ctx.kernel.context` | `ctx_put`, `ctx_get`, `ctx_delete`, `ctx_list`, `ctx_snapshot`, `ctx_recover`, `ctx_compact`, `ctx_clear` |
| `ctx.kernel.memory` | `mem_remember`, `mem_search`, `mem_get`, `mem_update`, `mem_delete`, `mem_list`, `mem_export`, `mem_import` |
| `ctx.kernel.storage` | `sto_mount`, `sto_mkdir`, `sto_create_file`, `sto_write`, `sto_read`, `sto_list`, `sto_delete`, `sto_stat`, `sto_history`, `sto_rollback`, `sto_share`, `sto_index`, `sto_retrieve` |
| `ctx.kernel.llm` | `llm_chat`, `llm_complete`, `llm_embed`, `llm_status`, `llm_cancel` |
| `ctx.kernel.tool` | `tool_call`, `tool_list`, `tool_describe`, `tool_load_manifest`, `tool_unload`, `tool_register_builtin`, `tool_status`, `tool_cancel` |
| `ctx.kernel.skill` | `skill_call`, `skill_list`, `skill_describe`, `skill_status`, `skill_cancel` |
| `ctx.kernel.access` | access decision facade; not a queued system call |

## Example

```python
result = await ctx.kernel.context.put("phase", "started")
if not result.success:
    return {"success": False, "error_code": result.error_code}
```
