# Real Integration Verification

Default tests verify contracts and stable fail-fast behavior. Real dependency
verification is opt-in and must not be replaced by simulated success.

## ROS2

```bash
AGENTIC_VERIFY_REAL_ROS2=1 PYTHONPATH=. pytest -q tests/test_real_integration_contracts.py::test_real_ros2_bridge_contract_is_opt_in_and_never_simulated
scripts/verify_real_ros2.sh
```

Requires `ros2` CLI and AgenticOS bridge services. Missing dependencies report
`UNVERIFIED_REAL_DEPENDENCY`.

The script prints:

```text
CHECK_NAME=real_ros2_bridge
REQUIRED_ENV=AGENTIC_VERIFY_REAL_ROS2=1
CONFIG_PATH=...
PROVIDER_STATUS=...
RESULT=PASS|FAIL|UNVERIFIED_REAL_DEPENDENCY
ERROR_CODE=...
NEXT_ACTION=...
```

## LLM

```bash
AGENTIC_VERIFY_REAL_LLM=1 \
AGENTIC_REAL_LLM_BASE_URL=https://provider.example/v1 \
AGENTIC_REAL_LLM_API_KEY=... \
AGENTIC_REAL_LLM_MODEL=model-name \
PYTHONPATH=. pytest -q tests/test_real_integration_contracts.py::test_real_llm_provider_contract_is_opt_in_and_never_simulated
```

Secrets must come from environment variables or a credential helper and must
not be written to code, docs, logs, commits, or snapshots.

`verify_real_llm.sh` prints the same fixed fields and never prints the API key
value.

## Human Queue

```bash
AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1 \
AGENTIC_REAL_HUMAN_QUEUE_ROOT=/opt/agentic/var/human \
PYTHONPATH=. pytest -q tests/test_real_integration_contracts.py::test_real_human_queue_contract_is_opt_in_and_never_auto_answers
```

An operator must append a matching response. The runtime never auto-fills an
answer.

`verify_real_human.sh` writes a real queue request and waits for an external
answer when `AGENTIC_VERIFY_REAL_HUMAN_QUEUE=1`; otherwise it reports
`UNVERIFIED_REAL_DEPENDENCY`.

## Environment-Aware Scheduler

Scheduler LLM verification:

```bash
AGENTIC_VERIFY_REAL_SCHEDULER_LLM=1 \
AGENTIC_REAL_LLM_BASE_URL=https://provider.example/v1 \
AGENTIC_REAL_LLM_API_KEY=... \
AGENTIC_REAL_LLM_MODEL=model-name \
scripts/verify_real_scheduler_llm.sh
```

This submits a scheduler planning goal through
`KernelService.execute_request(..., LLMQuery(...))`, validates the returned
TaskGraph schema, then dispatches a scheduler `ContextQuery` TaskNode through
the real KernelService/SQLite context manager to produce the verified reuse
fact. The follow-up fact-reuse graph requires a real LLM fusion explanation
validated by `fusion_reasoning.schema.json`. Both LLM calls must emit
`scheduler.llm.real_call_completed`, and the reused fact must carry a real
source syscall ID and AuditLogger ID.

Scheduler capability verification:

```bash
AGENTIC_VERIFY_REAL_SCHEDULER_CAPABILITY=1 \
scripts/verify_real_scheduler_capability.sh
```

This submits a real TaskGraph to the environment-aware scheduler and dispatches
a capability TaskNode through `CapabilityDispatchAdapter` and the existing
KernelService/runtime capability path. Missing bridge or capability backends
report `UNVERIFIED_REAL_DEPENDENCY` with exit code `2`.
The script sources `/opt/ros/humble/setup.bash` and
`/home/ubuntu/agentic_ws/install/setup.bash` when present so the ROS2 CLI can
resolve the real `agentic_msgs` interfaces and bridge packages. Override those
paths with `AGENTIC_ROS2_SETUP` and `AGENTIC_ROS2_BRIDGE_SETUP` if the bridge
overlay lives elsewhere. By default this does not start a bridge or emulate
robot state: if `/agentic/robot/get_state` or the selected capability action is
absent from the live ROS graph, the script returns `ROS_SERVICE_UNAVAILABLE` or
`ROS_ACTION_UNAVAILABLE` before dispatch. Set
`AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE=1` only when you want the verifier
to temporarily start the real read-only `state_bridge_node` for the duration of
the check; the process is cleaned up when the script exits. That preflight
uses a short ROS discovery retry window controlled by
`AGENTIC_VERIFY_ROS_DISCOVERY_ATTEMPTS` and
`AGENTIC_VERIFY_ROS_DISCOVERY_RETRY_DELAY_S`. `NEXT_ACTION` includes the
required interface name, the number of visible ROS services/actions, and the
exact ROS graph query command, for example
`required=/agentic/robot/get_state`, `visible_services=0`, and
`command=ros2 service list`. For the read-only state bridge service, it also
prints `start_command=ros2 run agentic_capability_bridge state_bridge_node`,
the bridge executable probe such as
`bridge_executable=agentic_capability_bridge/state_bridge_node:available`, and
`executable_command=ros2 pkg executables agentic_capability_bridge`. When the
opt-in auto-start path is used, `NEXT_ACTION` includes
`auto_start_readonly_state_bridge=` and the verifier log path.
When the interface is present, the script still runs the scheduler dispatch
path; if the state bridge is present but no real camera/arm/gripper backend is
visible the result remains
`ROS_BRIDGE_UNAVAILABLE`. In that dispatched case, `NEXT_ACTION` includes the
short bridge reason from the matching AuditLogger record so the missing real
backend evidence is visible without inspecting raw logs. When the bridge
returns structured readiness details, `NEXT_ACTION` also includes
`bridge_missing=` entries such as missing camera topics, arm backend topic, or
gripper topic. The verifier also appends a compact `ros_graph=` summary for
backend-unavailable results, including live node/topic/service/action counts,
whether `state_bridge_node` is visible, and whether the configured camera,
arm, and gripper candidate topics are present. It also appends
`profile_dependencies=` from `AGENTIC_VERIFY_BRIDGE_PROFILE_FILE` so the next
operator action can be based on the configured camera launch candidates,
arm topic/service candidates, and action-group file presence rather than
guesswork. The profile summary includes `camera_launch_files_present=` so a
missing launch artifact is distinguishable from an installed-but-stopped camera
backend. It also classifies `camera_backend=`, `arm_backend=`, and
`gripper_backend=` so an installed-but-stopped backend is distinguishable from
missing profile artifacts. `next_backend_steps=` gives compact action labels
such as `start_camera_launch` and `start_arm_servo_controller`; the verifier
does not execute those backend start actions automatically. `backend_step_hints=`
maps those labels to non-executing operator guidance, including the read-only
state-bridge opt-in, the first configured camera launch file, and
operator-gated real arm/servo startup.
A PASS also requires traceability evidence: the
`scheduler.node.dispatched` event must include the real KernelSyscall ID and
resource lease IDs, `KernelService.recent_syscalls()` must contain the matching
capability syscall, and the AuditLogger must contain that syscall audit record.

Checkpointable scheduler preemption uses the same real capability path:

```text
KernelService.checkpoint_request
  -> RobotCapabilityManager
  -> RuntimeRobotCapabilityBackend
  -> SkillExecutor.checkpoint_capability
  -> Ros2CliBridgeClient checkpoint service call
  -> /agentic/capability/checkpoint
```

The active ROS2 bridge source under
`/home/ubuntu/agentic_ws/ros2_bridge_src` defines
`agentic_msgs/srv/CheckpointCapability`. The current inspection bridge exposes
that service. Runtime robot capability dispatch passes the kernel syscall ID as
the runtime skill call ID and as the inspection bridge `request_id`, so a
checkpoint request for syscall `X` can only match active bridge progress for
request `X`. The inspection bridge returns `SCHEDULER_PREEMPTION_UNSUPPORTED`
when no matching active progress exists, and it must not report success without
preserved progress.

Static guard:

```bash
scripts/verify_no_fake_mock.sh
```

The guard scans production sources, scripts, apps, bridge packages, and tests
for forbidden non-real success paths. Documented negative tests and rejection
guards require narrow allowlist entries with reasons.
