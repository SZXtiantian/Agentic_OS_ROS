# Permissions, Safety, and Audit

Dangerous robot actions must pass through the full Runtime chain.

## Execution order

1. JSON Schema input validation
2. App manifest permission check
3. Kernel access/intervention
4. Safety guard
5. Resource lock
6. Timeout/cancellation
7. Backend dispatch
8. Audit/syscall/session recording
9. Resource lock release

## Resource locks

| Resource | Typical capability |
| --- | --- |
| `base` | Navigation |
| `camera` | Inspection, observation, photo capture |
| `arm` | Named arm actions |
| `gripper` | Gripper control |
| `color_block_detector` | Color-block detection/verification |

## Audit

Audit logs are JSONL records containing app, session, skill, args, permission, safety, resource lock, backend, status, error code, and duration.
