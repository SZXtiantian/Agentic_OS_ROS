# Access, Intervention, And Audit

The default access posture is deny-by-default for private resources, external
LLM calls, human asks, robot motion, and dangerous management operations.

## Dangerous Operations

| Area | Operations |
|---|---|
| Robot | navigation, arm motion, gripper control, stop-adjacent hardware action |
| Human | ask, status, cancel, operator intervention |
| Storage | delete, rollback, share, overwrite, protected mount/write |
| Memory | export, import, delete, bulk-changing operations |
| Tool | load manifest, unload, register external/builtin management |
| LLM | external provider chat, complete, embed |
| Context | recover, clear, delete, large checkpoint changes |

Dangerous operations require explicit permission and, when irreversible, a real
intervention provider. The default intervention provider denies and records
`ACCESS_INTERVENTION_REQUIRED`.

Human operator flow currently uses the real `file_queue` provider. The runtime
writes an ask request, waits for an external operator response, supports status
and cancel, records audit events, and returns `HUMAN_OPERATOR_TIMEOUT` when no
answer arrives. It never fills an answer automatically.

## Audit Fields

Audit/events include action, operation type, agent, session or syscall id,
provider, success, error code, reason, intervention metadata, and sanitized
details. Prompts, private memory content, and secrets must not be emitted.
