# Error Codes

Stable errors are part of the real-only contract.

| Code | Meaning |
|---|---|
| `TASK_INPUT_FIELD_UNSUPPORTED` | A production task input included a simulated-mode field. |
| `CONFIG_VALUE_UNSUPPORTED` | Runtime config named an unsupported or simulated value. |
| `ROS_BRIDGE_MODE_UNSUPPORTED` | Config selected a real bridge mode not implemented by the runtime factory. |
| `ROS_BRIDGE_UNAVAILABLE` | ROS2 CLI or required bridge service/action is unavailable. |
| `ROS_SERVICE_UNAVAILABLE` | A ROS2 service call could not reach the required service. |
| `ROS_ACTION_UNAVAILABLE` | A ROS2 action goal could not reach the required action. |
| `ROS_HTTP_BRIDGE_UNCONFIGURED` | HTTP bridge mode lacks required endpoint config. |
| `ROS_HTTP_BRIDGE_UNAVAILABLE` | HTTP bridge endpoint is unreachable. |
| `ROS_WS_BRIDGE_UNCONFIGURED` | WebSocket bridge mode lacks required endpoint config. |
| `ROS_WS_BRIDGE_UNAVAILABLE` | WebSocket bridge endpoint is unreachable. |
| `LLM_PROVIDER_UNSUPPORTED` | LLM provider/backend is not implemented as an available mode. |
| `LLM_PROVIDER_UNCONFIGURED` | LLM provider is missing base URL, key, model, or equivalent config. |
| `LLM_PROVIDER_DEPENDENCY_MISSING` | Optional provider package is missing. |
| `LLM_PROVIDER_REQUEST_FAILED` | Real remote/local LLM provider request failed. |
| `LLMCHAT_UNAVAILABLE` | AgentContext has no Runtime-owned `RuntimeServer.llm_chat` facade available. |
| `LLM_RESPONSE_INVALID` | Runtime-owned LLM facade returned a non-JSON-plan response shape. |
| `HELLO_WORLD_LLM_REQUIRED` | `hello_world_agent` could not plan because the system LLM is required. |
| `HELLO_WORLD_LLM_PLAN_INVALID` | `hello_world_agent` received an invalid constrained JSON plan. |
| `COLOR_BLOCK_LLM_PLAN_REQUIRED` | `color_block_grasper_agent` requires system LLM planning from natural language. |
| `COLOR_BLOCK_LLM_PLAN_INVALID` | `color_block_grasper_agent` received a constrained JSON plan that failed deterministic validation. |
| `COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE` | The real post-pick held-block verification backend is unavailable, missing, or not wired through the Agentic bridge. |
| `COLOR_BLOCK_PICK_VERIFICATION_FAILED` | Pick execution did not produce independent evidence that the requested color block is held by the gripper. |
| `HUMAN_PROVIDER_UNCONFIGURED` | No real human provider is configured. |
| `HUMAN_BACKEND_UNAVAILABLE` | Runtime human backend is unavailable. |
| `HUMAN_OPERATOR_TIMEOUT` | Human request timed out without an answer. |
| `HUMAN_CANCELLED` | Human request was cancelled. |
| `INTERVENTION_PROVIDER_UNCONFIGURED` | Required intervention provider is not configured. |
| `ACCESS_DENIED` | Access policy denied the operation. |
| `ACCESS_INTERVENTION_REQUIRED` | A dangerous operation needs real operator approval. |
| `SYSCALL_NOT_FOUND` | Cancel/status requested a missing active syscall or call id. |
| `SKILL_BACKEND_UNAVAILABLE` | Kernel skill manager is not wired to a real runtime backend. |
| `CAPABILITY_CONTRACT_VIOLATION` | A provider claimed availability for an unimplemented/reserved mode. |
| `UNVERIFIED_REAL_DEPENDENCY` | Real dependency verification was not configured or dependency is absent. |
