# Error Codes

Stable errors are part of the real-only contract.

| Code | Meaning |
|---|---|
| `TASK_INPUT_FIELD_UNSUPPORTED` | A production task input included a simulated-mode field. |
| `CONFIG_VALUE_UNSUPPORTED` | Runtime config named an unsupported or simulated value. |
| `ROS2_CLI_MISSING` | ROS2 CLI is not installed or not sourced for status/preflight. |
| `ROS_BRIDGE_MODE_UNSUPPORTED` | Config selected a real bridge mode not implemented by the runtime factory. |
| `ROS_BRIDGE_UNAVAILABLE` | Required ROS2 bridge service/action is unavailable. |
| `ROS_SERVICE_UNAVAILABLE` | A ROS2 service call could not reach the required service. |
| `ROS_ACTION_UNAVAILABLE` | A ROS2 action goal could not reach the required action. |
| `LLM_PROVIDER_UNCONFIGURED` | LLM provider is missing base URL, key, model, or equivalent config. |
| `LLM_PROVIDER_DEPENDENCY_MISSING` | Optional provider package is missing. |
| `LLM_PROVIDER_ERROR` | Real remote/local LLM provider failed. |
| `HUMAN_BACKEND_UNAVAILABLE` | No real human channel is configured. |
| `HUMAN_TIMEOUT` | Human request timed out without an answer. |
| `HUMAN_CANCELLED` | Human request was cancelled. |
| `ACCESS_DENIED` | Access policy denied the operation. |
| `ACCESS_INTERVENTION_REQUIRED` | A dangerous operation needs real operator approval. |
| `SYSCALL_NOT_FOUND` | Cancel/status requested a missing active syscall or call id. |
| `SKILL_BACKEND_UNAVAILABLE` | Kernel skill manager is not wired to a real runtime backend. |
| `UNVERIFIED_REAL_DEPENDENCY` | Real dependency verification was not configured or dependency is absent. |
