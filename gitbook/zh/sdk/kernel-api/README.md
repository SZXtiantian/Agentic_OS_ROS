# Agentic System Calls

`ctx.kernel.*` 是 Agentic System Call facade。它把 Python 调用转换成 Kernel 可调度、可审计的 system call operation。

普通 Agent App 先使用 Agentic SDK，例如 `ctx.robot.*`、`ctx.memory.*`、`ctx.report.*`。只有当 App 需要直接操作 Kernel context、memory、storage、LLM、tool 或 skill 调度时，才使用 `ctx.kernel.*`。

## Call Model

```text
ctx.kernel.storage.write(...)
  -> StorageQuery(operation_type="sto_write")
  -> Kernel scheduler / executor
  -> storage manager
  -> KernelSDKResult
```

## Result

大多数 `ctx.kernel.*` 调用返回：

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

`ctx.kernel.access.*` 是 access manager facade，返回 access decision dict，不进入 queued system call。

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
