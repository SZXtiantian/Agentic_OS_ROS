# Kernel Syscalls

Agent Apps use `ctx.kernel.*` and high-level `ctx.*` facades. Each call becomes
a typed query, typed syscall, scheduler lane entry, manager dispatch, provider
result, and audit/status event.

## Namespaces

| Namespace | Main operations |
|---|---|
| `context` | `ctx_put`, `ctx_get`, `ctx_list`, `ctx_delete`, `ctx_snapshot`, `ctx_recover`, `ctx_compact`, `ctx_clear` |
| `memory` | `mem_remember`, `mem_get`, `mem_search`, `mem_update`, `mem_delete`, `mem_list`, `mem_export`, `mem_import` |
| `storage` | `sto_mount`, `sto_mkdir`, `sto_create_file`, `sto_write`, `sto_read`, `sto_list`, `sto_delete`, `sto_stat`, `sto_history`, `sto_rollback`, `sto_share`, `sto_index`, `sto_retrieve` |
| `tool` | `tool_call`, `tool_list`, `tool_describe`, `tool_load_manifest`, `tool_unload`, `tool_register_builtin`, `tool_status`, `tool_cancel` |
| `skill` | `skill_list`, `skill_describe`, `skill_call`, `skill_status`, `skill_cancel` |
| `llm` | `llm_chat`, `llm_complete`, `llm_embed`, `llm_status`, `llm_cancel` |
| `human` | `human.ask`, `human_status`, `human_cancel` |
| `robot` | runtime skill/capability calls for state, navigation, perception, arm, gripper, and stop |

## Lifecycle

Every syscall has a `syscall_id`, queue name, status, timeout, response, and
recent status record. Cancel requests match exact `syscall_id` or provider
`call_id`; missing calls return `SYSCALL_NOT_FOUND`.
