# Runtime Real-Only Foundation

Agentic Runtime now exposes only real provider/backend execution paths. CLI,
SDK, app invocation, session scheduling, and runtime config do not provide a
simulated runtime mode.

## Production Surface

- `agentic-runtime status` and `agentic-runtime run-app` accept real-only
  operation. `--real` is a no-op marker where retained for scripts.
- `agentic`, `agentic chat`, and `agentic photo` do not expose simulated mode.
- `RuntimeServer.create()` has no simulated-mode parameter.
- `AppInvoker`, `SessionRunner`, and `SingleRobotScheduler` reject simulated
  task fields with `TASK_INPUT_FIELD_UNSUPPORTED`.
- `RuntimeConfig.load()` rejects `ros_bridge_mode` or `backend/type` values
  that name simulated providers.

## Success And Failure

A success result means a real provider/backend/service executed. Missing ROS2,
LLM, human, storage, memory, tool, or skill dependencies return stable errors
and appear in status/audit. Real integration checks that are not configured
must report `UNVERIFIED_REAL_DEPENDENCY`; they must not pass through simulated
success.

## Validation

```bash
PYTHONPATH=. pytest -q
scripts/verify_foundation.sh
scripts/verify_capability_truth.sh
scripts/verify_real_ros2.sh
scripts/verify_real_llm.sh
scripts/verify_real_human.sh
```
