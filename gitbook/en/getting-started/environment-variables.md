# Environment Variables Configuration

Common environment variables:

| Variable | Purpose |
| --- | --- |
| `AGENTIC_RUNTIME_SRC` | Runtime source root |
| `AGENTIC_APP_ROOT` | Agent App root |
| `AGENTIC_SKILL_PROVIDER_ROOT` | System skills root |
| `AGENTIC_HOME` | Install root, default `/opt/agentic` |
| `AGENTIC_VAR` | Runtime state root for audit, memory, session, reports |
| `AGENTIC_SESSION_ROOT` | Session/syscall storage root |
| `AGENTIC_STORAGE_ROOT` | Runtime storage root |
| `AGENTIC_CONTEXT_ROOT` | Runtime context root |
| `AGENTIC_REPORT_LOG` | `report.say` file output path |
| `AGENTIC_OPERATOR_INTERVENTION_APPROVED` | Operator intervention approval switch |
| `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION` | Allows real arm motion |
| `AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION` | Allows real pick/place manipulation |

## Real-only contract

Runtime rejects backend/type values such as `mock`, `fake`, `stub`, `dummy`, or `simulated`. Missing real dependencies must return structured errors such as `ROS_BRIDGE_UNAVAILABLE` or `UNVERIFIED_REAL_DEPENDENCY`.
