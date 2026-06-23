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
- `implemented_modes`
- `available_modes`
- `unsupported_modes`
- `reserved_modes`

`available_modes` may contain only implemented, real modes. It must not overlap
with `unsupported_modes` or `reserved_modes`.

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
