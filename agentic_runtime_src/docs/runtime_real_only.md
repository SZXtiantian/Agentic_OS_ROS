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

## Current Foundation-Complete Availability

- ROS bridge: `cli` is the only available bridge mode, and only when the real
  `ros2` CLI is present. `service`, `action`, `topic`, `http`, and `websocket`
  are classified as unsupported and return `ROS_BRIDGE_MODE_UNSUPPORTED`.
- LLM: OpenAI-compatible, vLLM OpenAI-compatible, and LiteLLM-compatible
  backends become available only after real config and dependencies pass
  preflight. HuggingFace and generic local backends are reserved.
- Human operator: `file_queue` is implemented. `console`, `http`, and
  `websocket` are reserved and are not advertised as available.
- Memory, context, storage, tool, and skill namespaces report their available
  modes through `KernelService.status()["providers"]`.

## Validation

```bash
PYTHONPATH=. pytest -q
scripts/verify_foundation.sh
scripts/verify_capability_truth.sh
scripts/verify_real_ros2.sh
scripts/verify_real_llm.sh
scripts/verify_real_human.sh
scripts/verify_real_scheduler_llm.sh
scripts/verify_real_scheduler_capability.sh
scripts/verify_no_fake_mock.sh
```

## Scheduler Real-Only Contract

The `env_aware_priority_dag` kernel policy keeps the same real-only contract.
TaskGraph planning and fusion-plan explanation use runtime-owned `LLMQuery`
syscalls; capability TaskNodes use typed kernel queries submitted through
`KernelService.execute_request`. Missing providers or bridge backends return
structured errors such as `SCHEDULER_LLM_REAL_PROVIDER_REQUIRED`,
`SCHEDULER_CAPABILITY_UNAVAILABLE`, or `UNVERIFIED_REAL_DEPENDENCY`.
The real scheduler capability verifier does not start or emulate ROS2 bridges
by default: if the selected service/action is absent from the live ROS graph it
returns `ROS_SERVICE_UNAVAILABLE` or `ROS_ACTION_UNAVAILABLE` with the required
interface, visible graph count, and query command in `NEXT_ACTION`, for example
`required=/agentic/robot/get_state`, `visible_services=0`, and
`command=ros2 service list`. The preflight uses a short ROS discovery retry
window controlled by `AGENTIC_VERIFY_ROS_DISCOVERY_ATTEMPTS` and
`AGENTIC_VERIFY_ROS_DISCOVERY_RETRY_DELAY_S`. Set
`AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE=1` to temporarily start the real
read-only `state_bridge_node` during the verifier run. For the read-only state
bridge service, it also prints
`start_command=ros2 run agentic_capability_bridge state_bridge_node`,
`bridge_executable=agentic_capability_bridge/state_bridge_node:available`,
`executable_command=ros2 pkg executables agentic_capability_bridge`, and
`auto_start_readonly_state_bridge=` when that opt-in path is used. Backend
unavailable results also include a compact `ros_graph=` summary with live
node/topic/service/action counts and configured camera/arm/gripper topic
visibility. They also include `profile_dependencies=` from
`AGENTIC_VERIFY_BRIDGE_PROFILE_FILE`, summarizing configured camera launch
candidates, `camera_launch_files_present=`, arm topic/service candidates,
action-group file presence, and compact `camera_backend=`, `arm_backend=`, and
`gripper_backend=` status labels. `next_backend_steps=` contains action labels
only, and `backend_step_hints=` translates them into non-executing operator
guidance. The verifier still does not start camera, arm, or gripper backends
automatically; arm/servo startup remains operator-gated.

Environment facts are reusable only when they carry traceable syscall and audit
metadata from a real capability result. LLM planning output cannot create
physical facts such as `cup_pose`. Current generic cup detection, pickup,
held-verification, and delivery capabilities are still real backend gaps; cup
reuse must remain unavailable until those bridge/HAL paths exist.
