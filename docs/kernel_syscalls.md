# Kernel Syscalls

Last updated: 2026-06-23

Agent Apps call kernel capabilities through `ctx.kernel.*`. Public syscalls return a `KernelResponse` shape: `success`, `data`, `response_message`, `error_code`, and `metadata`.

`ctx.kernel.cancel(syscall_id)` cancels only a syscall still waiting in the kernel queue. Missing, empty, already-finished, or manager-local active calls return `SYSCALL_NOT_FOUND`; manager-specific cancellation remains available through `ctx.kernel.llm.cancel`, `ctx.kernel.skill.cancel`, `ctx.kernel.tool.cancel`, and human cancel paths where the backend supports them.

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

OpenAI-compatible and vLLM-compatible LLM providers require explicit `base_url`, `api_key` or `api_key_env`, and `model`. LiteLLM, HuggingFace, and local providers require an explicit `model` before dependency or service checks. Provider `name` is only an internal route name and is not used as a model fallback.

The runtime dispatcher LLM facade also treats missing provider fields as unconfigured: no hardcoded base URL or model is injected when `models.yaml` and environment variables omit them.

Skill manifests with `backend.type` set to `mock`, `fake`, `stub`, or `dummy` are rejected during registry loading with `SKILL_BACKEND_SIMULATED_DISABLED` or manifest validation failure; they are never registered as executable runtime capabilities.

Context `ctx_compact` is structural JSON truncation over stored context entries. It is not an LLM semantic summary; `status()["context"]["compact_policy"]` reports `mode: structural_truncation`, `semantic_summary: false`, and `llm_required: false`.

Storage `sto_retrieve` is lexical SQLite FTS by default and returns `retrieval_mode: lexical_fts` with `semantic: false`. Semantic/vector retrieval may only be marked available when a real embedding/vector provider is configured; otherwise `status()["storage"]["semantic_retrieval"]` reports `STORAGE_SEMANTIC_PROVIDER_UNCONFIGURED`.

Human requests are durable JSONL queue records under the runtime human channel root. Operators or integration services must append a matching response by `correlation_id`; the runtime never invents an answer.

LLM status exposes provider configuration state and active `call_id`s. Cancelling an unknown LLM call returns `SYSCALL_NOT_FOUND`; cancelling an active call returns a cancel-request acknowledgement and the in-flight syscall returns `LLM_CANCELLED` once control returns from the provider call.

Skill calls may pass an explicit `call_id` through `ctx.kernel.skill.call(..., call_id="...")`. `ctx.kernel.skill.cancel(call_id)` cancels only the matching active runtime call in the current session; missing call IDs return `SYSCALL_NOT_FOUND`, while session-level cancel remains available for compatibility when no `call_id` is supplied.

Human ask runs through the runtime `human.ask` skill backend with timeout and correlation/call ID metadata. When no explicit `correlation_id` is supplied, the runtime uses the skill `call_id` as the durable queue correlation ID, so JSONL requests, status, and cancel requests refer to the same active operation. `human.cancel` forwards the same `call_id`/`correlation_id` to the runtime cancellation manager; unavailable managers fail with `SKILL_BACKEND_UNAVAILABLE`, and missing active calls return `SYSCALL_NOT_FOUND`.

## Permissions And Intervention

High-risk operations go through access/intervention/audit:

- `storage.delete`, `storage.rollback`, `storage.share`, and overwrite.
- `memory.delete`, `memory.export`, and `memory.import`.
- `tool.load_manifest`, `tool.unload`, and `tool.register_builtin`.
- robot motion skills routed through `robot_motion`.
- `human.ask`.
- external LLM provider calls.

Without an operator intervention backend, high-risk operations return `ACCESS_INTERVENTION_REQUIRED`.

## Audit Events

Kernel hook events are visible under `KernelService.status()["events"]["recent"]`. Sensitive payload keys such as prompts, messages, content, data, tokens, secrets, and passwords are redacted or omitted.

| Event | Emitted for |
| --- | --- |
| `context.audit` | context put/get/delete/list/snapshot/recover/compact/clear; compact events include `compact_mode: structural_truncation` |
| `memory.audit` | memory delete/export/import success and failure |
| `storage.audit` | storage delete/rollback/share success and failure |
| `tool.audit` | tool manifest load, unload, and builtin registration success and failure |
| `llm.audit` | provider attempts, provider unconfigured/errors, batch attempts, time-slice attempts, and LLM cancel requests |
| `human.audit` | human ask/cancel requests, backend unavailable, timeout, cancellation, and answered results |
| `skill.audit` | skill call/list/describe/status/cancel results |
| `robot.audit` | robot motion/sensor capability results, including ROS bridge unavailable and permission-denied failures |

## Builtin Tools

The kernel registers only real builtin tools:

- `calculator.add`
- `format_report.markdown`
- `file_digest.sha256`

Robot, ROS2, Nav2, MoveIt, arm, gripper, perception, and `/cmd_vel` names are rejected as generic tools.

`tool_cancel` uses the ToolManager active call registry. Unknown call IDs return `SYSCALL_NOT_FOUND`. For running tools, the manager sets a cooperative `_cancel_event` in the handler args and returns `cancel_requested`; a handler that observes the event exits with `TOOL_CANCELLED`. Non-cooperative handlers are not reported as successfully stopped.

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
pytest -q tests/test_kernel_syscall_async.py tests/test_robot_safety_regression.py
pytest -q tests/test_no_simulated_production_paths.py tests/test_runtime_real_defaults.py
pytest -q tests/test_real_integration_contracts.py -rs
python scripts/check_no_runtime_rclpy_imports.py
scripts/run_tests.sh
```

Real integration contracts are opt-in and never substitute fake success. Without the required environment they skip as `UNVERIFIED_*`:

- `AGENTIC_VERIFY_REAL_ROS2=1` verifies a real ROS2 bridge through `Ros2CliBridgeClient`.
- `AGENTIC_VERIFY_REAL_LLM=1` plus `AGENTIC_REAL_LLM_BASE_URL`, `AGENTIC_REAL_LLM_API_KEY`, and `AGENTIC_REAL_LLM_MODEL` verifies a real OpenAI-compatible provider.
- `AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1` verifies a real file-backed human queue with an external operator/service response.

Latest full local verification for this document update baseline:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pytest -q
# 382 passed, 3 skipped
scripts/run_tests.sh
# 382 passed, 3 deselected; Agentic OS MVP checks passed.
```
