# Codex Kernel Phase 2 Progress

## Current Status

- Current K2 PR: K2-PR-18 complete.
- Current gate: K2-Gate 5 complete.
- Next K2 PR: none; Phase 2 complete.

## K2-PR-00：修复开发机可移植性和打包范围

- Verification-first result: partially satisfied before changes; target tests passed on this machine, but config and tests still depended on historical `/home/ubuntu/agentic_ws/src` and staging paths.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/config/`
  - `/home/ubuntu/AIOS/README.md`
- Changed files:
  - `pyproject.toml`
  - `configs/runtime.yaml`
  - `agentic_runtime/config.py`
  - `agentic_runtime/llm/config.py`
  - `agentic_runtime/nl_cli.py`
  - `agentic_runtime/nl_gateway.py`
  - `agentic_runtime/photo_cli.py`
  - `agentic_runtime/skill_executor/dispatcher.py`
  - `tests/conftest.py`
  - `tests/test_config.py`
  - `tests/test_architecture_module_layout.py`
  - `tests/test_deployment_layout.py`
  - `tests/test_dispatcher_no_direct_ros.py`
  - `tests/test_dispatcher_plan_schema.py`
  - `tests/test_app_invoker_dispatch.py`
  - `tests/test_dispatcher_rejects_unsafe_motion.py`
  - `tests/test_dispatcher_routes_robot_photographer.py`
  - `tests/test_capability_registry.py`
  - `tests/test_robot_photographer_agent.py`
- Implemented:
  - Added `agentic_os*` to setuptools package discovery.
  - Made `configs/runtime.yaml` repo-relative.
  - Updated `RuntimeConfig.load()` lookup order to explicit config, `AGENTIC_RUNTIME_CONFIG`, `AGENTIC_RUNTIME_SRC/configs/runtime.yaml`, repo config, then `AGENTIC_HOME/etc/agentic.yaml`.
  - Removed default `/home/ubuntu/configs/*` and staging fallback config lookup.
  - Added portable pytest environment defaults and fixtures.
  - Replaced default development path assumptions in runtime CLI helpers and affected tests.
- Target tests:
  - `python -m pytest tests/test_config.py tests/test_architecture_module_layout.py tests/test_deployment_layout.py -q` -> `22 passed`.
  - `python -m pytest tests/test_kernel_*.py tests/test_access_manager.py -q` -> `71 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `229 passed`.
- Safety boundary check:
  - `python scripts/check_forbidden_imports.py` -> `forbidden import/static guard ok`.
- Remaining risks:
  - Historical docs and real robot scripts still mention deployment paths such as `/opt/agentic` and legacy workspaces by design.

## K2-PR-01：建立 AIOS 对照开发地图和安全守卫

- Verification-first result: partially satisfied before changes; existing dispatcher guard passed, but the requested map and dedicated runtime/kernel `rclpy` import guard did not exist.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/{syscall,scheduler,context,llm_core,memory,storage,tool,hooks}`
  - Agentic kernel directories under `agentic_os/kernel/`
- Changed files:
  - `docs/kernel/AIOS_KERNEL_PORTING_MAP.md`
  - `scripts/check_no_runtime_rclpy_imports.py`
  - `tests/test_no_runtime_rclpy_imports.py`
- Implemented:
  - Added human-readable AIOS to Agentic kernel porting map.
  - Added AST-based `rclpy` import scanner for `agentic_os` and `agentic_runtime`.
  - Added tests proving runtime/kernel imports are rejected and `ros2_bridge_src` is not scanned.
- Target tests:
  - `python agentic_runtime_src/scripts/check_no_runtime_rclpy_imports.py` -> `runtime/kernel rclpy import guard ok`.
  - `python -m pytest tests/test_dispatcher_no_direct_ros.py tests/test_no_runtime_rclpy_imports.py -q` -> `4 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `229 passed`.
- Safety boundary check:
  - `python scripts/check_forbidden_imports.py` -> `forbidden import/static guard ok`.
- Remaining risks:
  - None for Gate 0.

## K2-Gate 0 Summary

- Completed K2 PRs: K2-PR-00, K2-PR-01.
- Verified without code changes: previous kernel subset behavior remained green.
- Implemented changes: portable path/config fixes, package discovery, AIOS porting map, dedicated runtime/kernel `rclpy` import guard.
- Commands run:
  - `python -m pytest tests/test_config.py tests/test_architecture_module_layout.py tests/test_deployment_layout.py -q`
  - `python -m pytest tests/test_kernel_*.py tests/test_access_manager.py -q`
  - `python agentic_runtime_src/scripts/check_no_runtime_rclpy_imports.py`
  - `python -m pytest tests/test_dispatcher_no_direct_ros.py tests/test_no_runtime_rclpy_imports.py -q`
  - `python scripts/check_forbidden_imports.py`
  - `python -m pytest -q`
- Passing tests:
  - K2-PR-00 target: `22 passed`
  - Kernel subset: `71 passed`
  - K2-PR-01 guard tests: `4 passed`
  - Full runtime tests: `229 passed`
- Remaining risks:
  - Real ROS2/hardware acceptance was not run for Gate 0; default tests remain mock/portable.
- Next gate:
  - Continue with K2-Gate 1 from K2-PR-02 syscall lifecycle.

## K2-PR-02：补齐 KernelSyscall 生命周期和状态机

- Verification-first result: partially satisfied before changes; target tests passed, but `suspended/resuming`, cancel/reject helpers, `aid/agent_id`, `KernelResponse.ok/error`, scheduler expiry, and timeout helper coverage were missing.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/syscall/syscall.py`
  - `/home/ubuntu/AIOS/aios/syscall/factory.py`
  - `/home/ubuntu/AIOS/aios/syscall/schema.py`
  - `/home/ubuntu/AIOS/aios/syscall/{llm,memory,storage,tool}.py`
  - `/home/ubuntu/AIOS/aios/syscall/types/`
- Changed files:
  - `agentic_os/kernel/system_call/models.py`
  - `agentic_os/kernel/system_call/schema.py`
  - `agentic_os/kernel/system_call/executor.py`
  - `agentic_os/kernel/scheduler/base.py`
  - `tests/test_kernel_syscall_async.py`
  - `tests/test_kernel_scheduler_threads.py`
- Implemented:
  - Added complete lifecycle statuses and transition helpers.
  - Added `aid` and `agent_id` fields while preserving `agent_name` and `KernelSyscall.create()`.
  - Added `timeout()`, `cancel()`, `reject()`, expiry checks, and structured response helpers.
  - Scheduler now skips cancelled syscalls and times out expired syscalls before manager execution.
- Target tests:
  - `python -m pytest tests/test_kernel_syscall_async.py tests/test_kernel_syscall_factory.py -q` -> `11 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `242 passed`.
- Safety boundary check:
  - `python agentic_runtime_src/scripts/check_no_runtime_rclpy_imports.py` -> `runtime/kernel rclpy import guard ok`.
- Remaining risks:
  - Cooperative cancellation hooks for long-running robot managers remain owned by the safe SkillExecutor/RobotCapability path and are further exercised in robot safety tests.

## K2-PR-03：强化 KernelQueueStore 和 scheduler lane contract

- Verification-first result: partially satisfied before changes; FIFO queues existed, but metrics snapshot, `peek`, `drain`, `remove`, backpressure, bounded policies, and lane batching fields were missing.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/scheduler/base.py`
  - `/home/ubuntu/AIOS/aios/scheduler/fifo_scheduler.py`
  - `/home/ubuntu/AIOS/aios/scheduler/rr_scheduler.py`
  - `/home/ubuntu/AIOS/aios/hooks/`
- Changed files:
  - `agentic_os/kernel/hooks/queues.py`
  - `agentic_os/kernel/hooks/__init__.py`
  - `agentic_os/kernel/scheduler/lanes.py`
  - `tests/test_kernel_hooks_queues.py`
  - `tests/test_kernel_scheduler_threads.py`
  - `tests/test_kernel_scheduler_robot_lanes.py`
- Implemented:
  - Replaced simple queue wrapper with centralized `deque + Condition` store.
  - Added queue policies, metrics, backpressure, `peek`, `size`, `drain`, and `remove`.
  - Added emergency stop priority behavior for robot motion queues.
  - Added scheduler lane batching fields and LLM batch defaults.
- Target tests:
  - `python -m pytest tests/test_kernel_hooks_queues.py tests/test_kernel_scheduler_robot_lanes.py -q` -> `13 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `242 passed`.
- Safety boundary check:
  - `python scripts/check_forbidden_imports.py` -> `forbidden import/static guard ok`.
- Remaining risks:
  - Queue policy defaults remain permissive for most lanes to preserve existing behavior; stricter deployment policies can be passed through configuration.

## K2-PR-04：完善 FIFO Scheduler processing threads

- Verification-first result: partially satisfied before changes; start/stop and manager dispatch existed, but manager timeout mapping, lazy KernelService start, repeated start/stop coverage, and runtime shutdown path were missing.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/scheduler/base.py`
  - `/home/ubuntu/AIOS/aios/scheduler/fifo_scheduler.py`
- Changed files:
  - `agentic_os/kernel/scheduler/base.py`
  - `agentic_runtime/kernel_service/app.py`
  - `agentic_runtime/server.py`
  - `tests/test_kernel_scheduler_threads.py`
  - `tests/test_runtime_kernel_service.py`
- Implemented:
  - Scheduler now maps manager `TimeoutError` to `KERNEL_MANAGER_TIMEOUT`.
  - Scheduler success/failure paths use syscall lifecycle helpers.
  - `KernelService.execute_request()` lazily starts the scheduler when needed.
  - Added `RuntimeServer.shutdown()` to stop kernel scheduler threads.
  - Added repeated start/stop no-leak tests.
- Target tests:
  - `python -m pytest tests/test_kernel_scheduler_threads.py tests/test_kernel_e2e_syscall_flow.py -q` -> `11 passed`.
  - `python -m pytest tests/test_runtime_kernel_service.py -q` -> `8 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `242 passed`.
- Safety boundary check:
  - `python agentic_runtime_src/scripts/check_no_runtime_rclpy_imports.py` -> `runtime/kernel rclpy import guard ok`.
- Remaining risks:
  - Runtime users should call `RuntimeServer.shutdown()` or `KernelService.stop()` in long-running embedded tests to release lazy-started scheduler threads.

## K2-Gate 1 Summary

- Completed K2 PRs: K2-PR-02, K2-PR-03, K2-PR-04.
- Verified without code changes: existing typed syscall classes and robot lane routing remained intact.
- Implemented changes: syscall lifecycle helpers, queue policies/metrics, scheduler manager timeout mapping, KernelService lazy start, runtime shutdown.
- Commands run:
  - `python -m pytest tests/test_kernel_syscall_async.py tests/test_kernel_syscall_factory.py -q`
  - `python -m pytest tests/test_kernel_hooks_queues.py tests/test_kernel_scheduler_robot_lanes.py -q`
  - `python -m pytest tests/test_kernel_scheduler_threads.py tests/test_kernel_e2e_syscall_flow.py -q`
  - `python -m pytest tests/test_runtime_kernel_service.py -q`
  - `python -m pytest tests/test_kernel_syscall_async.py tests/test_kernel_syscall_factory.py tests/test_kernel_hooks_queues.py tests/test_kernel_scheduler_threads.py tests/test_kernel_scheduler_robot_lanes.py tests/test_kernel_e2e_syscall_flow.py -q`
  - `python agentic_runtime_src/scripts/check_no_runtime_rclpy_imports.py`
  - `python scripts/check_forbidden_imports.py`
  - `python -m pytest -q`
- Passing tests:
  - K2-PR-02 target: `11 passed`
  - K2-PR-03 target: `13 passed`
  - K2-PR-04 target: `11 passed`
  - Runtime KernelService tests: `8 passed`
  - Gate 1 combo: `35 passed`
  - Full runtime tests: `242 passed`
- Remaining risks:
  - Real robot/hardware cancellation remains opt-in acceptance work; mock safety regressions are still the default boundary.
- Next gate:
  - Continue with K2-Gate 2 from K2-PR-05 LLM lane batching.

## K2-PR-05：实现 LLM lane batching

- Verification-first result: partially satisfied before changes; lane fields existed but scheduler did not collect/execute batches and `LLMAdapter` had no batch API.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/scheduler/fifo_scheduler.py`
  - `/home/ubuntu/AIOS/aios/llm_core/adapter.py`
  - `/home/ubuntu/AIOS/aios/llm_core/routing.py`
- Changed files:
  - `agentic_os/kernel/scheduler/base.py`
  - `agentic_os/kernel/scheduler/lanes.py`
  - `agentic_os/kernel/llm_core/adapter.py`
  - `agentic_os/kernel/llm_core/provider.py`
  - `tests/test_kernel_llm_core.py`
  - `tests/test_kernel_scheduler_threads.py`
- Implemented:
  - Added batch collection and execution for batchable lanes.
  - Added `LLMAdapter.complete_batch()` and `address_batch()`.
  - Added provider batch fallback to sequential `complete()`.
  - Preserved ordered responses and per-item failure isolation.
- Target tests:
  - `python -m pytest tests/test_kernel_llm_core.py tests/test_kernel_scheduler_threads.py -q` -> `21 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `259 passed`.
- Safety boundary check:
  - `python agentic_runtime_src/scripts/check_no_runtime_rclpy_imports.py` -> `runtime/kernel rclpy import guard ok`.
- Remaining risks:
  - Real provider batch behavior remains optional-provider integration work; default tests use fake providers only.

## K2-PR-06：实现 RoundRobin Scheduler 的 LLM preemption 与 text context switch

- Verification-first result: partially satisfied before changes; `can_preempt_lane()` existed, but RR did not time-slice/resume LLM syscalls.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/scheduler/rr_scheduler.py`
  - AIOS context references from `/home/ubuntu/AIOS/aios/context/`
- Changed files:
  - `agentic_os/kernel/context/generation.py`
  - `agentic_os/kernel/context/simple_generation.py`
  - `agentic_os/kernel/llm_core/adapter.py`
  - `agentic_os/kernel/scheduler/rr_scheduler.py`
  - `tests/test_kernel_generation_context.py`
- Implemented:
  - Added richer `GenerationSnapshot` fields for text context switch.
  - Added `LLMAdapter.complete_with_time_slice()`.
  - Added RR scheduler suspend/requeue/resume flow for preemptible LLM lane.
  - Non-streaming providers are marked `non_preemptible_llm_call` and run to completion.
  - Robot motion remains non-preemptible and does not use generation context.
- Target tests:
  - `python -m pytest tests/test_kernel_generation_context.py tests/test_kernel_scheduler_robot_lanes.py -q` -> `12 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `259 passed`.
- Safety boundary check:
  - `python scripts/check_forbidden_imports.py` -> `forbidden import/static guard ok`.
- Remaining risks:
  - This is text snapshot switching only; KV/logits switching is intentionally out of scope.

## K2-PR-07：KernelService 配置驱动组合

- Verification-first result: partially satisfied before changes; KernelService was still hardcoded to `mock-kernel`.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/config/`
  - `/home/ubuntu/AIOS/aios/llm_core/utils.py`
- Changed files:
  - `configs/runtime.yaml`
  - `agentic_runtime/config.py`
  - `agentic_runtime/kernel_service/app.py`
  - `tests/test_config.py`
  - `tests/test_runtime_kernel_service.py`
- Implemented:
  - Added `kernel:` runtime config block.
  - Added `RuntimeConfig.kernel`.
  - KernelService now builds LLM adapter, scheduler, memory, storage, tool, and access-facing managers from config defaults.
  - Added RR scheduler selection by config.
  - Kernel status includes a sanitized config summary without API keys.
- Target tests:
  - `python -m pytest tests/test_runtime_kernel_service.py tests/test_kernel_llm_core.py tests/test_config.py -q` -> `25 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `259 passed`.
- Safety boundary check:
  - status secret-leak test passed; no API key is rendered.
- Remaining risks:
  - Advanced provider config validation remains lightweight for MVP; invalid provider backends return structured errors at runtime.

## K2-PR-08：补齐 LLM Core provider matrix 和 response normalization

- Verification-first result: partially satisfied before changes; provider shell existed, but LiteLLM/vLLM/HF matrix, normalization, JSON validation, and smart routing sort were incomplete.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/llm_core/adapter.py`
  - `/home/ubuntu/AIOS/aios/llm_core/local.py`
  - `/home/ubuntu/AIOS/aios/llm_core/routing.py`
  - `/home/ubuntu/AIOS/aios/llm_core/utils.py`
- Changed files:
  - `agentic_os/kernel/llm_core/schema.py`
  - `agentic_os/kernel/llm_core/provider.py`
  - `agentic_os/kernel/llm_core/utils.py`
  - `agentic_os/kernel/llm_core/routing.py`
  - `agentic_os/kernel/llm_core/adapter.py`
  - `agentic_os/kernel/llm_core/errors.py`
  - `agentic_os/kernel/llm_core/__init__.py`
  - `tests/test_kernel_llm_core.py`
- Implemented:
  - Extended `LLMConfig` provider metadata/capability fields.
  - Added LiteLLM, vLLM OpenAI-compatible, and HuggingFace provider shells.
  - Optional dependencies are imported only inside provider methods.
  - Added OpenAI/LiteLLM/HF response normalization and JSON response validation.
  - Added deterministic quality/cost smart routing.
  - Adapter fallback annotates final errors with candidate metadata.
- Target tests:
  - `python -m pytest tests/test_kernel_llm_core.py -q` -> `16 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `259 passed`.
- Safety boundary check:
  - optional dependency import check: `litellm=False`, `openai=False`, `transformers=False`, `chromadb=False`, `mcp=False`, `redis=False`.
- Remaining risks:
  - Real LiteLLM/vLLM/HF calls are not run by default and require explicit integration configuration.

## K2-Gate 2 Summary

- Completed K2 PRs: K2-PR-05, K2-PR-06, K2-PR-07, K2-PR-08.
- Verified without code changes: existing mock LLM routing and SDK LLM calls remained compatible.
- Implemented changes: LLM batch scheduling, RR text context switch, config-driven KernelService, provider matrix, response normalization.
- Commands run:
  - `python -m pytest tests/test_kernel_llm_core.py tests/test_kernel_scheduler_threads.py -q`
  - `python -m pytest tests/test_kernel_generation_context.py tests/test_kernel_scheduler_robot_lanes.py -q`
  - `python -m pytest tests/test_runtime_kernel_service.py tests/test_kernel_llm_core.py tests/test_config.py -q`
  - `python -m pytest tests/test_kernel_llm_core.py -q`
  - `python -m pytest tests/test_kernel_llm_core.py tests/test_kernel_scheduler_threads.py tests/test_kernel_generation_context.py tests/test_kernel_scheduler_robot_lanes.py tests/test_runtime_kernel_service.py tests/test_config.py -q`
  - optional dependency import check for `litellm`, `openai`, `transformers`, `chromadb`, `mcp`, `redis`
  - `python agentic_runtime_src/scripts/check_no_runtime_rclpy_imports.py`
  - `python agentic_runtime_src/scripts/check_forbidden_imports.py`
  - `python -m pytest -q`
- Passing tests:
  - K2-PR-05 target: `21 passed`
  - K2-PR-06 target: `12 passed`
  - K2-PR-07 target: `25 passed`
  - K2-PR-08 target: `16 passed`
  - Gate 2 combo: `54 passed`
  - Full runtime tests: `259 passed`
- Remaining risks:
  - Default tests intentionally avoid network and real LLM providers.
- Next gate:
  - Continue with K2-Gate 3 from K2-PR-09 memory two-tier/compressed blocks.

## Resume Point

- Phase 2 K2-PR-00 through K2-PR-18 complete.
- Before continuing, inspect this file, the Phase 2 task document, and `git diff`.

## K2-PR-09：实现 MemoryManager 两级记忆与压缩块

- Verification-first result: partially satisfied before changes; memory syscalls worked, but eviction only dropped old notes and did not preserve compressed long-term blocks.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/memory/`
  - Agentic kernel memory manager/provider tests.
- Changed files:
  - `agentic_os/kernel/memory/manager.py`
  - `agentic_os/kernel/memory/block.py`
  - `agentic_os/kernel/memory/compression.py`
  - `agentic_os/kernel/memory/eviction.py`
  - `agentic_os/kernel/memory/__init__.py`
  - `tests/test_kernel_memory_manager_v2.py`
- Implemented:
  - Added `CompressedMemoryBlock` for second-tier memory.
  - Added token-budget and block-count eviction knobs.
  - Added deterministic summary compression for evicted notes.
  - Added optional `StorageManager` persistence under `memory_blocks/{agent}/{block}.json`.
  - Retrieval now searches active RAM notes, compressed blocks, persistent provider results, and stored block summaries.
- Target tests:
  - `python -m pytest tests/test_kernel_memory_manager_v2.py tests/test_kernel_storage_syscalls.py -q` -> `16 passed`.
- Safety boundary check:
  - Memory code uses kernel storage/access abstractions only and does not import `rclpy`.
- Remaining risks:
  - Compression is deterministic MVP summarization, not semantic compression from a model provider.

## K2-PR-10：实现向量检索接口与 robot metadata filter

- Verification-first result: partially satisfied before changes; keyword retrieval existed but no vector provider, embedding abstraction, or robot metadata filters were present.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/memory/`
- Changed files:
  - `agentic_os/kernel/memory/embeddings.py`
  - `agentic_os/kernel/memory/retrievers.py`
  - `agentic_os/kernel/memory/providers/vector.py`
  - `agentic_os/kernel/memory/providers/__init__.py`
  - `agentic_os/kernel/memory/__init__.py`
  - `tests/test_kernel_memory_manager_v2.py`
- Implemented:
  - Added deterministic hash embedding provider and cosine similarity helper.
  - Added hybrid lexical/vector retriever.
  - Added metadata filters for `place_id`, `robot_id`, `frame_id`, `retention_class`, and `privacy`.
  - Added optional Chroma provider wrapper with structured dependency-missing errors when disabled or unavailable.
- Target tests:
  - `python -m pytest tests/test_kernel_memory_manager_v2.py -q` -> `11 passed`.
- Safety boundary check:
  - Optional `chromadb` import is lazy and not required for default runtime tests.
- Remaining risks:
  - Real Chroma persistence is not exercised unless `enabled=True` and the dependency is installed.

## K2-PR-11：补齐 StorageManager LSFS adapter 与版本化语义

- Verification-first result: partially satisfied before changes; storage syscalls existed, but LSFS adapter methods were mostly placeholders.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/storage/`
- Changed files:
  - `agentic_os/kernel/storage/manager.py`
  - `agentic_os/kernel/storage/filesystem/lsfs_adapter.py`
  - `tests/test_kernel_storage_syscalls.py`
- Implemented:
  - Implemented LSFS mount, create file, create directory, write, retrieve, rollback, share, and status over `StorageManager`.
  - Added overwrite version names and rollback support.
  - Added retrieve snippets, scores, and metadata.
  - Expanded unsafe path protection to `task_logs`, `config(s)`, and bridge profile paths.
- Target tests:
  - `python -m pytest tests/test_kernel_storage_syscalls.py tests/test_storage_manager.py -q` -> `16 passed`.
- Safety boundary check:
  - Storage access checks still route high-risk overwrite/delete/rollback/share through `AccessManager`.
- Remaining risks:
  - LSFS sharing is an in-process MVP policy map, not a distributed capability grant service.

## K2-PR-12：实现 AccessManager 生产语义

- Verification-first result: partially satisfied before changes; static access checks and test intervention existed, but persistent ACL, dynamic ACL, operator queues, and decision logs were missing.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/`
  - Existing Agentic access/storage/tool call paths.
- Changed files:
  - `agentic_os/kernel/access/policy.py`
  - `agentic_os/kernel/access/store.py`
  - `agentic_os/kernel/access/decision_log.py`
  - `agentic_os/kernel/access/intervention.py`
  - `agentic_os/kernel/access/manager.py`
  - `agentic_os/kernel/access/__init__.py`
  - `tests/test_access_manager.py`
- Implemented:
  - Added `AccessRule` schema with subject, group, action, resource type/id pattern, effect, expiration, and reason.
  - Added `InMemoryAccessStore` and `JsonFileAccessStore`.
  - Added in-memory and JSONL decision logs with metadata redaction for secrets/tokens/keys/passwords.
  - Added decision IDs to `AccessDecision`.
  - Added dynamic allow/deny/require-intervention evaluation while preserving hard static denies.
  - Added `ConsoleInterventionProvider` and `FileQueueInterventionProvider`.
  - Expanded high-risk operations to storage rollback/share/overwrite, access privilege change, tool admin/install, bridge profile changes, and real-hardware robot motion.
- Target tests:
  - `python -m pytest tests/test_access_manager.py tests/test_permission_manager.py -q` -> `15 passed`.
  - `python -m pytest tests/test_access_manager.py tests/test_kernel_storage_syscalls.py tests/test_kernel_tool_dynamic_loading.py -q` -> `28 passed`.
- Full/portable tests:
  - `python -m pytest -q` -> `271 passed`.
- Safety boundary check:
  - `python scripts/check_no_runtime_rclpy_imports.py` -> `runtime/kernel rclpy import guard ok`.
  - `python scripts/check_forbidden_imports.py` -> `forbidden import/static guard ok`.
- Remaining risks:
  - File-queued interventions require an external operator UI/process to approve or replay queued items.

## K2-Gate 3 Summary

- Completed K2 PRs: K2-PR-09, K2-PR-10, K2-PR-11, K2-PR-12.
- Verified without code changes: existing memory, storage, tool, and permission tests remained compatible.
- Implemented changes: two-tier compressed memory, hybrid vector retrieval, LSFS adapter, versioned storage semantics, persistent/dynamic ACL, decision logs, and operator intervention providers.
- Commands run:
  - `python -m pytest tests/test_kernel_memory_manager_v2.py tests/test_kernel_storage_syscalls.py -q`
  - `python -m pytest tests/test_kernel_memory_manager_v2.py -q`
  - `python -m pytest tests/test_kernel_storage_syscalls.py tests/test_storage_manager.py -q`
  - `python -m pytest tests/test_access_manager.py tests/test_permission_manager.py -q`
  - `python -m pytest tests/test_access_manager.py tests/test_kernel_storage_syscalls.py tests/test_kernel_tool_dynamic_loading.py -q`
  - `python -m pytest tests/test_kernel_memory_manager_v2.py tests/test_kernel_storage_syscalls.py tests/test_storage_manager.py tests/test_access_manager.py -q`
  - `python -m pytest -q`
  - `python scripts/check_no_runtime_rclpy_imports.py`
  - `python scripts/check_forbidden_imports.py`
- Passing tests:
  - K2-PR-09 target: `16 passed`
  - K2-PR-10 target: `11 passed`
  - K2-PR-11 target: `16 passed`
  - K2-PR-12 access/permission target: `15 passed`
  - K2-PR-12 cross-manager target: `28 passed`
  - Gate 3 combo: `40 passed`
  - Full runtime tests: `271 passed`
- Remaining risks:
  - Real robot and external operator approval acceptance remains deployment work; default tests use mock/local providers.
- Next gate:
  - Continue with K2-Gate 4 from K2-PR-13 tool manager dynamic loading and sandboxing.

## K2-PR-13：ToolManager sandbox / MCP lifecycle / conflict policy

- Verification-first result: partially satisfied before changes; dynamic loading, conflict lock, and robot prefix denial existed, but manifest `version/mcp`, sandbox validation, MCP lifecycle, and install access checks were incomplete.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/tool/manager.py`
  - `/home/ubuntu/AIOS/aios/tool/mcp_server.py`
  - `/home/ubuntu/AIOS/aios/tool/virtual_env/`
- Changed files:
  - `agentic_os/kernel/tool/manifest.py`
  - `agentic_os/kernel/tool/sandbox.py`
  - `agentic_os/kernel/tool/mcp_server.py`
  - `agentic_os/kernel/tool/manager.py`
  - `tests/test_kernel_tool_dynamic_loading.py`
  - `tests/test_tool_manager.py`
- Implemented:
  - Added `version` and `mcp` manifest fields.
  - Added `ToolSandboxPolicy` validation for disabled modes, network denial, filesystem modes, and workspace containment.
  - Implemented disabled-by-default MCP lifecycle: `start`, `stop`, `status`, `list_tools`, and `call_tool`.
  - Added tool install access check through `AccessManager`.
  - Preserved conflict locks and added tool lifecycle event records in `ToolManager.status()`.
  - Added `/cmd_vel` backdoor coverage.
- Target tests:
  - `python -m pytest tests/test_kernel_tool_dynamic_loading.py tests/test_tool_manager.py tests/test_dispatcher_no_direct_ros.py -q` -> `14 passed`.
- Safety boundary check:
  - Generic `robot.*`, ROS2/Nav2/MoveIt/perception/direct velocity tools remain forbidden.
- Remaining risks:
  - `subprocess`, `venv`, and `container` sandbox modes are explicitly disabled by default and need separate runtime policy before use.

## K2-PR-14：RobotCapabilityManager 接入真实 bridge lifecycle，但保持 ROS2 边界

- Verification-first result: partially satisfied before changes; runtime/kernel already avoided `rclpy` and bridge dry-run planning existed, but RobotCapabilityManager lacked a typed backend protocol and BridgeInstaller/BridgeManager did not expose the full lifecycle.
- Status: implemented.
- Changed files:
  - `agentic_os/kernel/capability/manager.py`
  - `agentic_os/kernel/capability/__init__.py`
  - `agentic_runtime/kernel_service/robot_backend.py`
  - `agentic_runtime/kernel_service/app.py`
  - `agentic_runtime/hardware_adapter/ros2_profile.py`
  - `agentic_runtime/hardware_adapter/installer.py`
  - `agentic_runtime/hardware_adapter/bridge_manager.py`
  - `tests/test_bridge_manager.py`
  - `tests/test_robot_safety_regression.py`
- Implemented:
  - Added `RobotCapabilityBackend` protocol and wired `RobotCapabilityManager` through `execute_capability()`.
  - Added runtime-provided `RuntimeRobotCapabilityBackend` that converts kernel robot syscalls back into the safe `SkillExecutor` chain.
  - KernelService now injects the runtime robot backend for robot motion and robot sensor managers when a runtime server is present.
  - Extended `Ros2BridgeProfile` with workspace, packages, launch, capability, and safety fields.
  - Added BridgeInstaller lifecycle methods: `validate`, `build_workspace`, `activate`, `rollback`, and `status`.
  - Added BridgeManager lifecycle facade: `plan`, `validate`, `build_workspace`, `activate`, and `rollback`.
  - Preserved dry-run default and environment opt-in for real build execution.
- Target tests:
  - `python -m pytest tests/test_bridge_manager.py tests/test_ros2_cli_bridge_client.py tests/test_robot_safety_regression.py tests/test_skill_executor.py -q` -> `34 passed`.
  - `python -m pytest tests/test_dispatcher_no_direct_ros.py -q` -> `1 passed`.
- Safety boundary check:
  - Runtime/Kernel still use CLI/mock bridge clients and safe SkillExecutor; no runtime/kernel `rclpy` import was introduced.
- Remaining risks:
  - Real bridge builds still require explicit `AGENTIC_ALLOW_BRIDGE_INSTALL=1` and a valid ROS2/colcon environment.

## K2-PR-15：Kernel observability / hooks / audit integration

- Verification-first result: partially satisfied before changes; queue metrics and recent syscalls existed, but there was no shared hook event sink, manager latency events, access/tool hook events, or content redaction for kernel audit args.
- Status: implemented.
- AIOS reference inspected:
  - `/home/ubuntu/AIOS/aios/hooks/`
  - `/home/ubuntu/AIOS/aios/scheduler/`
- Changed files:
  - `agentic_os/kernel/hooks/events.py`
  - `agentic_os/kernel/hooks/__init__.py`
  - `agentic_os/kernel/hooks/queues.py`
  - `agentic_os/kernel/scheduler/base.py`
  - `agentic_os/kernel/scheduler/fifo_scheduler.py`
  - `agentic_os/kernel/scheduler/rr_scheduler.py`
  - `agentic_os/kernel/system_call/executor.py`
  - `agentic_os/kernel/access/manager.py`
  - `agentic_os/kernel/tool/manager.py`
  - `agentic_runtime/kernel_service/app.py`
  - `agentic_runtime/skill_executor/executor.py`
  - `agentic_runtime/server.py`
  - `tests/test_kernel_hooks_queues.py`
  - `tests/test_kernel_observability.py`
- Implemented:
  - Added `InMemoryKernelEventSink` and sanitized `KernelHookEvent` records.
  - QueueStore now emits queue add/dequeue/reject/cancel events.
  - Scheduler now emits syscall and manager lifecycle events for success, failure, timeout, and RR suspend/done flows.
  - SyscallExecutor emits `syscall.created` and timeout events.
  - AccessManager emits `access.checked`.
  - ToolManager emits `tool.started`, `tool.done`, and `tool.failed` into the shared event sink.
  - SkillExecutor can emit `robot.safety_checked`.
  - KernelService status now includes event summaries, manager status, LLM/storage/tool summaries, syscall IDs, manager keys, wait/duration, and audit IDs.
  - Kernel audit args are redacted for prompt/message/content/data/key/token/secret/password-like fields.
- Target tests:
  - `python -m pytest tests/test_kernel_observability.py tests/test_kernel_hooks_queues.py tests/test_runtime_kernel_service.py -q` -> `23 passed`.
- Safety boundary check:
  - Status and kernel audit records do not render full LLM messages or storage content by default.
- Remaining risks:
  - Event sink is in-memory MVP observability; production export to OpenTelemetry/Prometheus remains future work.

## K2-PR-16：SDK Facade 与 Agent API 稳定化

- Verification-first result: partially satisfied before changes; existing SDK robot/perception paths were stable and kernel LLM/storage wrappers existed, but there was no unified SDK result, memory search wrapper, storage retrieve wrapper, or SDK-level robot-tool denial test.
- Status: implemented.
- Changed files:
  - `agentic_runtime/sdk/kernel.py`
  - `agentic_runtime/sdk/__init__.py`
  - `agentic_runtime/kernel_service/app.py`
  - `tests/test_sdk.py`
- Implemented:
  - Added `KernelSDKResult` with `success`, `response`, `error_code`, `syscall_id`, `audit_id`, and `metadata`.
  - Kernel facade now wraps kernel execution results while preserving existing `result.success` and `result.metadata` access.
  - Added `ctx.kernel.memory.search()`.
  - Added `ctx.kernel.storage.retrieve()`.
  - KernelService returns `syscall_id` and `audit_id` in result metadata.
  - Added SDK test proving `ctx.kernel.tool.call("robot.navigate_to")` is forbidden while `ctx.robot.navigate_to()` still uses SkillExecutor.
- Target tests:
  - `python -m pytest tests/test_sdk.py tests/test_runtime_kernel_wrappers.py tests/test_robot_photographer_agent.py -q` -> `27 passed`.
- Safety boundary check:
  - Agent SDK still contains no `rclpy` import and no direct ROS topic strings.
- Remaining risks:
  - `KernelSDKResult.raw` exposes the in-process execution object to Python callers; public docs should treat it as diagnostic/unstable.

## K2-Gate 4 Summary

- Completed K2 PRs: K2-PR-13, K2-PR-14, K2-PR-15, K2-PR-16.
- Verified without code changes: existing SkillExecutor robot safety chain, ROS2 CLI client parsing, and legacy SDK apps remained compatible.
- Implemented changes: tool sandbox/MCP lifecycle, robot capability backend wiring, bridge lifecycle facade, kernel hook events, observability status, audit redaction, and stable kernel SDK result wrappers.
- Commands run:
  - `python -m pytest tests/test_kernel_tool_dynamic_loading.py tests/test_tool_manager.py tests/test_dispatcher_no_direct_ros.py -q`
  - `python -m pytest tests/test_bridge_manager.py tests/test_ros2_cli_bridge_client.py tests/test_robot_safety_regression.py tests/test_skill_executor.py -q`
  - `python -m pytest tests/test_dispatcher_no_direct_ros.py -q`
  - `python -m pytest tests/test_kernel_observability.py tests/test_kernel_hooks_queues.py tests/test_runtime_kernel_service.py -q`
  - `python -m pytest tests/test_sdk.py tests/test_runtime_kernel_wrappers.py tests/test_robot_photographer_agent.py -q`
  - `python -m pytest tests/test_kernel_tool_dynamic_loading.py tests/test_tool_manager.py tests/test_dispatcher_no_direct_ros.py tests/test_bridge_manager.py tests/test_ros2_cli_bridge_client.py tests/test_robot_safety_regression.py tests/test_skill_executor.py tests/test_kernel_observability.py tests/test_kernel_hooks_queues.py tests/test_runtime_kernel_service.py tests/test_sdk.py tests/test_runtime_kernel_wrappers.py tests/test_robot_photographer_agent.py -q`
  - `python -m pytest -q`
  - `python scripts/check_no_runtime_rclpy_imports.py`
  - `python scripts/check_forbidden_imports.py`
- Passing tests:
  - K2-PR-13 target: `14 passed`
  - K2-PR-14 target: `34 passed`
  - K2-PR-14 direct ROS guard target: `1 passed`
  - K2-PR-15 target: `23 passed`
  - K2-PR-16 target: `27 passed`
  - Gate 4 combo: `98 passed`
  - Full runtime tests: `284 passed`
- Remaining risks:
  - Real ROS2 bridge lifecycle activation/build still requires opt-in environment and real ROS2/colcon installation.
- Next gate:
  - Continue with K2-Gate 5 from K2-PR-17 CI profiles and test layering.

## K2-PR-17：CI profiles 与测试分层

- Verification-first result: not satisfied before changes; pytest markers were not configured and the default test script ran unfiltered full pytest.
- Status: implemented.
- Changed files:
  - `pyproject.toml`
  - `scripts/run_tests.sh`
  - `tests/test_ci_profiles.py`
- Implemented:
  - Added pytest markers: `portable`, `integration`, `ros2`, and `hardware`.
  - Updated `scripts/run_tests.sh` to default to `pytest -m "not ros2 and not hardware" -q`.
  - Added `PYTEST_MARK_EXPR` override for ROS2/hardware/integration CI profiles.
  - Added regression tests proving marker definitions and default portable profile.
  - Verified real robot shell acceptances remain scripts outside default pytest collection.
- Target tests:
  - `python -m pytest tests/test_ci_profiles.py -q` -> `3 passed`.
  - `python -m pytest -m "not ros2 and not hardware" -q` -> `287 passed`.
- Safety boundary check:
  - Default Codex/CI command does not opt into ROS2 or hardware tests.
- Remaining risks:
  - No ROS2/hardware pytest tests are currently collected by default; future real-environment tests must be explicitly marked.

## K2-PR-18：最终验收和回归矩阵

- Verification-first result: all required final matrices passed after K2-PR-17.
- Status: verified.
- Changed files:
  - `docs/codex_kernel_phase2_progress.md`
- Verified capabilities:
  - KernelQuery -> Syscall -> Queue -> Scheduler -> Manager -> Response -> Audit path.
  - LLM lane batching and RR fake streaming suspend/resume.
  - Robot motion non-preemptible lane and generic tool robot denial.
  - Safe LSFS-compatible storage syscalls.
  - Two-tier memory, eviction, compressed blocks, and retrieval.
  - Tool dynamic loading, sandbox validation, MCP disabled default, and conflict lock.
  - Access ACL, intervention, and decision log.
  - Runtime/kernel `rclpy` boundary.
  - Default portable tests with no ROS2/hardware opt-in.
- Portable acceptance:
  - `python -m pytest -m "not ros2 and not hardware" -q` -> `287 passed`.
  - `python -m pytest tests/test_dispatcher_no_direct_ros.py -q` -> `1 passed`.
- Kernel acceptance:
  - `python -m pytest tests/test_kernel_syscall_async.py tests/test_kernel_syscall_factory.py tests/test_kernel_scheduler_threads.py tests/test_kernel_scheduler_robot_lanes.py tests/test_kernel_generation_context.py tests/test_kernel_llm_core.py tests/test_kernel_memory_manager_v2.py tests/test_kernel_storage_syscalls.py tests/test_kernel_tool_dynamic_loading.py tests/test_kernel_observability.py -q` -> `85 passed`.
- Safety acceptance:
  - `python -m pytest tests/test_dispatcher_no_direct_ros.py tests/test_robot_safety_regression.py tests/test_skill_executor.py tests/test_permission_manager.py tests/test_access_manager.py -q` -> `30 passed`.
- Additional guards:
  - `python scripts/check_no_runtime_rclpy_imports.py` -> `runtime/kernel rclpy import guard ok`.
  - `python scripts/check_forbidden_imports.py` -> `forbidden import/static guard ok`.
  - `scripts/run_tests.sh` -> `287 passed` plus filesystem/static guards.
- Remaining risks:
  - Real ROS2 and hardware acceptance scripts remain explicit opt-in and were not run in this portable final matrix.

## K2-Gate 5 Summary

- Completed K2 PRs: K2-PR-17, K2-PR-18.
- Verified without code changes: final K2-PR-18 acceptance was satisfied by the accumulated Phase 2 implementation plus K2-PR-17 test layering.
- Implemented changes: pytest CI markers, portable default test profile, and final matrix documentation.
- Commands run:
  - `python -m pytest tests/test_ci_profiles.py -q`
  - `python -m pytest -m "not ros2 and not hardware" -q`
  - `python -m pytest tests/test_dispatcher_no_direct_ros.py -q`
  - `python -m pytest tests/test_kernel_syscall_async.py tests/test_kernel_syscall_factory.py tests/test_kernel_scheduler_threads.py tests/test_kernel_scheduler_robot_lanes.py tests/test_kernel_generation_context.py tests/test_kernel_llm_core.py tests/test_kernel_memory_manager_v2.py tests/test_kernel_storage_syscalls.py tests/test_kernel_tool_dynamic_loading.py tests/test_kernel_observability.py -q`
  - `python -m pytest tests/test_dispatcher_no_direct_ros.py tests/test_robot_safety_regression.py tests/test_skill_executor.py tests/test_permission_manager.py tests/test_access_manager.py -q`
  - `python scripts/check_no_runtime_rclpy_imports.py`
  - `python scripts/check_forbidden_imports.py`
  - `scripts/run_tests.sh`
- Passing tests:
  - K2-PR-17 CI profile tests: `3 passed`
  - Portable final matrix: `287 passed`
  - Direct ROS guard final matrix: `1 passed`
  - Kernel final matrix: `85 passed`
  - Safety final matrix: `30 passed`
  - Default run script: `287 passed`
- Remaining risks:
  - ROS2/hardware acceptance requires explicit environment opt-in and real robot availability.
- Next gate:
  - None; Phase 2 is complete.
