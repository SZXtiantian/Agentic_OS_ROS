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

Production `RuntimeServer.create()` wires one shared kernel `AccessManager` and event sink into `KernelService`, the skill executor, runtime memory, runtime storage, runtime context, and runtime tool wrappers. Runtime session context snapshots and recovery therefore go through `ctx_snapshot`/`ctx_recover` access/audit instead of a separate unaudited manager instance. Runtime tool execution through the access-managed wrapper requires explicit `tool.execute` or tool-specific execute permission.

Context status exposes the real SQLite `path`/`db_path`, counts, `last_error`, and compact policy. Memory status exposes the real SQLite `path`/`db_path`, `fts_available`, `index`, and `last_error`. Memory import/export file failures return stable errors such as `MEMORY_IMPORT_INVALID_JSON`, `MEMORY_IMPORT_NOT_FOUND`, or `MEMORY_EXPORT_FAILED` and are emitted as `memory.audit` events.
Runtime `memory.remember` skill dispatch returns the real kernel/provider result; provider failures such as `MEMORY_PROVIDER_UNAVAILABLE` are propagated through the runtime memory adapter to the skill result and audit record instead of being converted to an empty success.
Runtime `memory.recall` skill dispatch uses the structured kernel result path; provider failures remain `MEMORY_PROVIDER_UNAVAILABLE` instead of being converted to successful `value: null`.
Runtime artifact writes check the kernel storage response before creating `ArtifactRecord`; storage provider failures preserve stable `STORAGE_*` error codes instead of surfacing as missing-field exceptions.
Runtime `report.say` writes to a real JSONL report sink at `AGENTIC_REPORT_LOG` or `AGENTIC_VAR/reports/report.jsonl`; write failures return `REPORT_BACKEND_UNAVAILABLE` and appear in bridge client status instead of returning stdout-only success.
ROS bridge `ask_human` responses use the same `success` contract as other public results: answered requests return `success: true`, bridge failures return their stable ROS error code with `success: false`, and unanswered responses without a backend error are `HUMAN_UNANSWERED`.
The kernel `HumanInteractionManager` normalizes legacy human backends that return only `answered`; non-object backend responses fail as `HUMAN_RESULT_INVALID`.

OpenAI-compatible and vLLM-compatible LLM providers require explicit `base_url`, `api_key` or `api_key_env`, and `model`. LiteLLM, HuggingFace, and local providers require an explicit `model` before dependency or service checks. Provider `name` is only an internal route name and is not used as a model fallback.
LiteLLM `llm_embed` uses the real `litellm.embedding(...)` API and never falls back to chat completion; missing `litellm` returns `LLM_PROVIDER_DEPENDENCY_MISSING`, provider failures return `LLM_PROVIDER_ERROR`, and malformed embedding responses return `LLM_RESPONSE_INVALID`.

The runtime dispatcher LLM facade also treats missing provider fields as unconfigured: no hardcoded base URL or model is injected when `models.yaml` and environment variables omit them. HTTP, DNS, socket, and other remote provider failures return `LLM_PROVIDER_ERROR`; request timeouts return `LLM_TIMEOUT`.

Skill manifests with `backend.type` set to `mock`, `fake`, `stub`, or `dummy` are rejected during registry loading with `SKILL_BACKEND_SIMULATED_DISABLED` or manifest validation failure; they are never registered as executable runtime capabilities.

Context `ctx_compact` is structural JSON truncation over stored context entries. It is not an LLM semantic summary; `status()["context"]["compact_policy"]` reports `mode: structural_truncation`, `semantic_summary: false`, and `llm_required: false`.

Context syscalls run through the kernel access manager and emit `access.checked` plus `context.audit`; audit events do not include stored context values. Direct syscall manager construction without a kernel access manager returns `ACCESS_MANAGER_UNAVAILABLE` before reading or mutating the SQLite provider.

Storage `sto_retrieve` is lexical SQLite FTS by default and returns `retrieval_mode: lexical_fts` with `semantic: false`. Semantic/vector retrieval may only be marked available when a real embedding/vector provider is configured; otherwise `status()["storage"]["semantic_retrieval"]` reports `STORAGE_SEMANTIC_PROVIDER_UNCONFIGURED`.
Storage share policies live in the persistent SQLite share registry; deleting a file removes its share entry, and querying share policy for a missing file returns `STORAGE_NOT_FOUND` instead of stale success.

Runtime ROS bridge status includes `bridge_client` when a runtime server is wired. The real `Ros2CliBridgeClient.status()` exposes `ros2_cli_available`, `last_command`, `last_success`, and `last_error` so missing `ros2`, unavailable services/actions, timeouts, and invalid bridge responses remain visible after fail-fast errors. Bridge clients without a real `status()` contract report `ROS_BRIDGE_STATUS_UNAVAILABLE`; non-object or invalid status payloads report `ROS_RESULT_INVALID` and emit `ros_bridge.status`. `agentic-runtime status --json` returns the same kernel status surface instead of the legacy monitor-only view.
Runtime CLI, photo CLI, and natural-language gateway bridge readiness failures use the same stable `ROS_BRIDGE_UNAVAILABLE` code; older `AGENTIC_BRIDGE_UNAVAILABLE` text is historical and must not be emitted by production entrypoints.

Human requests are durable JSONL queue records under the runtime human channel root. Operators or integration services must append a matching response by `correlation_id`; the runtime never invents an answer.

`human.ask` requires explicit `human.ask` permission in syscall metadata before the runtime backend is called. With permission present, it is still treated as an intervention-gated operation; without an operator intervention backend it returns `ACCESS_INTERVENTION_REQUIRED`.
If `HumanInteractionManager` is constructed without a kernel access manager, `human.ask` fails before the backend with `ACCESS_MANAGER_UNAVAILABLE`; cancel/status paths remain available for lifecycle inspection.
Legacy SDK/runtime `ctx.human.ask` also runs through `SkillExecutor` access/intervention before the JSONL queue backend. Without an access manager it fails with `ACCESS_MANAGER_UNAVAILABLE`; without intervention approval it fails with `ACCESS_INTERVENTION_REQUIRED` before writing a queue request.

Runtime robot motion skills such as `robot.navigate_to`, `robot.inspect_area`, `arm.move_named`, and `gripper.set` require both explicit robot permissions and operator intervention before safety checks or ROS bridge calls run. Without an intervention backend they fail with `ACCESS_INTERVENTION_REQUIRED` and emit audit/status evidence; `robot.stop` remains permission-gated but is not delayed by intervention.
If a `SkillExecutor` is constructed without a kernel `AccessManager`, managed robot/perception/gripper skills fail fast with `ACCESS_MANAGER_UNAVAILABLE` before any safety or ROS bridge call; production `RuntimeServer.create()` wires the shared access manager into the executor.
Robot capability backends must return an object with explicit `success`; malformed or non-object backend results fail as `ROBOT_RESULT_INVALID` and emit `robot.audit`.

LLM status exposes provider configuration state and active `call_id`s. `llm_status(call_id=...)` and `llm_cancel` inspect the LLM active-call registry; unknown call IDs return `SYSCALL_NOT_FOUND`. Cancelling an active call returns a cancel-request acknowledgement and the in-flight syscall returns `LLM_CANCELLED` once control returns from the provider call.

Configured external LLM provider calls require a kernel access manager and explicit `llm.external.call` permission in syscall metadata. Without an access manager the public syscall path returns `ACCESS_MANAGER_UNAVAILABLE` before any provider call. When a provider is configured and the permission is present, the call is still intervention-gated; without an operator intervention backend it returns `ACCESS_INTERVENTION_REQUIRED`. Missing provider configuration still fails as `LLM_PROVIDER_UNCONFIGURED` before any access prompt because no external call is attempted.

Skill calls may pass an explicit `call_id` through `ctx.kernel.skill.call(..., call_id="...")`. `ctx.kernel.skill.status(call_id=...)` and `ctx.kernel.skill.cancel(call_id)` inspect the runtime active-call registry; missing call IDs return `SYSCALL_NOT_FOUND`, while session-level cancel remains available for compatibility when no `call_id` is supplied.

Runtime skill backend responses must explicitly include `success` or, for human replies, `answered`. The kernel skill manager also rejects non-object responses or responses missing `success` with `SKILL_RESULT_INVALID`; these failures are audited instead of being treated as successful.

Human ask runs through the runtime `human.ask` skill backend with timeout and correlation/call ID metadata. When no explicit `correlation_id` is supplied, the runtime uses the skill `call_id` as the durable queue correlation ID, so JSONL requests, status, and cancel requests refer to the same active operation. `human.status(call_id=...)` and `human.cancel` inspect the active human/skill registry; unavailable managers fail with `SKILL_BACKEND_UNAVAILABLE`, and missing active calls return `SYSCALL_NOT_FOUND`.

Runtime app invocation results are contract-checked at the `AppInvoker`, `AppManager`, and `SessionRunner` boundaries. Direct app results must be objects with an explicit boolean `success`; session-wrapper results must contain `result.success` as a boolean. Non-object results, missing `success`, or non-boolean success fields fail with `APP_RESULT_INVALID` and are recorded as failed sessions instead of being inferred as successful.

## Permissions And Intervention

High-risk operations go through access/intervention/audit:

- `storage.delete`, `storage.rollback`, `storage.share`, and overwrite.
- `memory.delete`, `memory.export`, and `memory.import`.
- `tool.load_manifest`, `tool.unload`, and `tool.register_builtin`.
- robot motion skills routed through `robot_motion`.
- `human.ask`.
- external LLM provider calls.

Tool management never receives implicit admin rights from the manager. `tool.load_manifest` requires `tool.install` or `tool.load_manifest`, `tool.unload` requires `tool.uninstall` or `tool.unload`, and `tool.register_builtin` requires `tool.register_builtin`; `tool.manage` grants all three management actions. Direct manager construction without a kernel access manager returns `ACCESS_MANAGER_UNAVAILABLE` before registry changes. Missing permissions return `ACCESS_DENIED`. With permission present, these operations are still intervention-gated and emit `tool.audit`.

Without an operator intervention backend, high-risk operations that pass the permission check return `ACCESS_INTERVENTION_REQUIRED`.
Memory delete/export/import also require a kernel access manager; direct manager construction without one returns `ACCESS_MANAGER_UNAVAILABLE` and audits the rejected operation before touching the provider.
Storage overwrite/delete/rollback/share also require a kernel access manager; direct manager construction without one returns `ACCESS_MANAGER_UNAVAILABLE` and audits the rejected operation before mutating files or share policy.

## Audit Events

Kernel hook events are visible under `KernelService.status()["events"]["recent"]`. Sensitive payload keys such as prompts, messages, content, data, tokens, secrets, and passwords are redacted or omitted.

| Event | Emitted for |
| --- | --- |
| `context.audit` | context put/get/delete/list/snapshot/recover/compact/clear; compact events include `compact_mode: structural_truncation` |
| `memory.audit` | memory remember/get/search/list/update plus delete/export/import success and failure |
| `storage.audit` | storage mount/mkdir/create_file/write/read/list/stat/history/index/retrieve plus overwrite/delete/rollback/share success and failure |
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

`tool_status(call_id=...)` and `tool_cancel` use the ToolManager active call registry. Unknown call IDs return `SYSCALL_NOT_FOUND`. For running tools, the manager sets a cooperative `_cancel_event` in the handler args and returns `cancel_requested`; a handler that observes the event exits with `TOOL_CANCELLED`. Non-cooperative handlers are not reported as successfully stopped.

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
# 454 passed, 3 skipped
scripts/run_tests.sh
# 454 passed, 3 deselected; Agentic OS MVP checks passed.
```
