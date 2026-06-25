# Provider Contracts

`KernelService.status()["providers"]` is the runtime preflight surface for
real provider truth. Every namespace reports:

- `validate_config`
- `status`
- `health`
- `capabilities`
- `error_code`
- `missing`
- `details`
- `capability_evidence`
- `implemented_modes`
- `available_modes`
- `unsupported_modes`
- `reserved_modes`

`available_modes` may contain only implemented, real modes with tests and code
evidence. It must not overlap with `unsupported_modes` or `reserved_modes`.
Schema/config values that are not implemented must still appear in
`unsupported_modes` or `reserved_modes`, and selecting them must return a stable
error code.

## Current Provider Matrix

| Namespace | Implemented real mode | Reserved or unsupported |
|---|---|---|
| ROS bridge | `cli` when `ros2` CLI is present | `service`, `action`, `topic`, `http`, `websocket` |
| LLM | `openai_compatible`, `ollama_openai_compatible`, `vllm_openai_compatible`, `vllm`, `litellm`, `litellm_compatible` only when configured | `huggingface`, `hf`, `hflocal`, `local` |
| Human | `file_queue` | `console`, `http`, `websocket` |
| Context | `sqlite` | none |
| Memory | `sqlite_fts5` | `semantic_vector` |
| Storage | `local_fs`, `sqlite_fts5` | `semantic_vector` |
| Tool | `builtin` | `mcp` |
| Skill | `runtime_skill_backend` when a real `RuntimeServer` is wired | none |

## Error Contract

Providers that are not configured or healthy do not block unrelated namespaces
from starting. Their syscalls must fail with stable error codes and emit
status/audit evidence.

Key stable errors:

- ROS bridge mode outside `cli`: `ROS_BRIDGE_MODE_UNSUPPORTED`.
- ROS2 CLI absent for `cli`: `ROS_BRIDGE_UNAVAILABLE`.
- LLM reserved or unknown backend: `LLM_PROVIDER_UNSUPPORTED`.
- LLM missing config: `LLM_PROVIDER_UNCONFIGURED`.
- LLM optional dependency absent: `LLM_PROVIDER_DEPENDENCY_MISSING`.
- LLM remote/provider request failure: `LLM_PROVIDER_REQUEST_FAILED`.
- Agent App context has no Runtime-owned LLM facade: `LLMCHAT_UNAVAILABLE`.
- Natural-language tutorial app cannot produce a constrained JSON plan:
  `HELLO_WORLD_LLM_REQUIRED` or `COLOR_BLOCK_LLM_PLAN_REQUIRED`.
- Human queue timeout: `HUMAN_OPERATOR_TIMEOUT`.
- Real dependency verification not configured: `UNVERIFIED_REAL_DEPENDENCY`.

## Runtime LLM Facade Contract

Agent Apps consume system LLM capability through `ctx.llm.chat_json(...)`, which
delegates to `RuntimeServer.llm_chat`. Runtime/Kernel owns provider client
construction, config, secrets, and provider-specific request handling. Apps must
not import provider SDKs, instantiate provider clients, or read model keys.

Natural-language planning apps receive a constrained JSON plan from the facade
and then perform deterministic schema validation, policy validation, safety
checks, capability execution, memory/storage writes, and reporting. If the
facade or provider is unavailable, the app returns the stable LLM error. It
must not report success by switching to an app-local text parser.
