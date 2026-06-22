# Kernel Syscalls

Last updated: 2026-06-23

Agent Apps call kernel capabilities through `ctx.kernel.*`. Public syscalls return a `KernelResponse` shape: `success`, `data`, `response_message`, `error_code`, and `metadata`.

## Namespaces

| Namespace | Operations |
| --- | --- |
| `context` | `ctx_snapshot`, `ctx_recover`, `ctx_put`, `ctx_get`, `ctx_delete`, `ctx_list`, `ctx_compact`, `ctx_clear` |
| `memory` | `mem_remember`, `mem_add`, `mem_search`, `mem_get`, `mem_update`, `mem_delete`, `mem_list`, `mem_export`, `mem_import` |
| `storage` | `sto_mount`, `sto_mkdir`, `sto_create_file`, `sto_write`, `sto_read`, `sto_list`, `sto_delete`, `sto_stat`, `sto_history`, `sto_rollback`, `sto_retrieve`, `sto_share`, `sto_index` |
| `skill` | `skill_call`, `skill_list`, `skill_describe`, `skill_status`, `skill_cancel` |
| `tool` | `tool_call`, `tool_list`, `tool_describe`, `tool_load_manifest`, `tool_unload`, `tool_register_builtin`, `tool_status`, `tool_cancel` |
| `llm` | `llm_chat`, `llm_complete`, `llm_embed`, `llm_status`, `llm_cancel` |

## Real Providers

| Capability | Default provider | Unavailable behavior |
| --- | --- | --- |
| context | SQLite under `storage_root/.kernel_context` | `CONTEXT_PROVIDER_UNAVAILABLE` |
| memory | SQLite + FTS5 under `storage_root/.kernel_memory` | `MEMORY_PROVIDER_UNAVAILABLE` or `MEMORY_INDEX_UNAVAILABLE` |
| storage | local safe filesystem + version history + persistent SQLite FTS/share registry | `STORAGE_PROVIDER_UNAVAILABLE`, `STORAGE_INDEX_UNAVAILABLE`, or `STORAGE_SHARE_REGISTRY_UNAVAILABLE` |
| tool | builtin real tools plus manifest tools from `tool_root` | `TOOL_NOT_FOUND`, `TOOL_BACKEND_UNAVAILABLE`, or access error |
| skill | runtime `SkillExecutor` backend | `SKILL_BACKEND_UNAVAILABLE` |
| human | runtime file-backed operator queue through `human.ask` | `HUMAN_BACKEND_UNAVAILABLE`, `HUMAN_TIMEOUT`, or `HUMAN_CANCELLED` |
| llm | OpenAI-compatible/LiteLLM/HF/local configured provider | `LLM_PROVIDER_UNCONFIGURED`, `LLM_PROVIDER_DEPENDENCY_MISSING`, `LLM_PROVIDER_ERROR`, or `LLM_PROVIDER_UNAVAILABLE` |

No default mock LLM, memory, context, storage, tool, skill, or human provider is selected. Missing external services fail with stable error codes and appear in `KernelService.status()`.

Storage `sto_retrieve` is lexical SQLite FTS by default and returns `retrieval_mode: lexical_fts` with `semantic: false`. Semantic/vector retrieval may only be marked available when a real embedding/vector provider is configured; otherwise `status()["storage"]["semantic_retrieval"]` reports `STORAGE_SEMANTIC_PROVIDER_UNCONFIGURED`.

Human requests are durable JSONL queue records under the runtime human channel root. Operators or integration services must append a matching response by `correlation_id`; the runtime never invents an answer.

LLM status exposes provider configuration state and active `call_id`s. Cancelling an unknown LLM call returns `SYSCALL_NOT_FOUND`; cancelling an active call returns a cancel-request acknowledgement and the in-flight syscall returns `LLM_CANCELLED` once control returns from the provider call.

## Permissions And Intervention

High-risk operations go through access/intervention/audit:

- `storage.delete`, `storage.rollback`, `storage.share`, and overwrite.
- `memory.delete`, `memory.export`, and `memory.import`.
- `tool.load_manifest`, `tool.unload`, and `tool.register_builtin`.
- robot motion skills routed through `robot_motion`.
- `human.ask`.
- external LLM provider calls.

Without an operator intervention backend, high-risk operations return `ACCESS_INTERVENTION_REQUIRED`.

## Builtin Tools

The kernel registers only real builtin tools:

- `calculator.add`
- `format_report.markdown`
- `file_digest.sha256`

Robot, ROS2, Nav2, MoveIt, arm, gripper, perception, and `/cmd_vel` names are rejected as generic tools.

## Verification

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
pytest -q tests/test_kernel_context_syscalls.py
pytest -q tests/test_kernel_memory_sqlite_syscalls.py
pytest -q tests/test_kernel_storage_real_syscalls.py
pytest -q tests/test_kernel_tool_real_syscalls.py
pytest -q tests/test_kernel_skill_syscalls.py
pytest -q tests/test_kernel_llm_core.py tests/test_kernel_e2e_syscall_flow.py
pytest -q tests/test_human_queue_channel.py tests/test_kernel_human_backend.py
pytest -q tests/test_no_simulated_production_paths.py tests/test_runtime_real_defaults.py
python scripts/check_no_runtime_rclpy_imports.py
scripts/run_tests.sh
```
