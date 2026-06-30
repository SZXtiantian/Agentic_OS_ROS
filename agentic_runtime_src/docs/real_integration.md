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
