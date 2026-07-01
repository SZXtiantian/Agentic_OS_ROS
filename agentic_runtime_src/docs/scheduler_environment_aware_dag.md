# Environment-Aware Opportunistic Global DAG Scheduler

The AgenticOS environment-aware DAG scheduler lives in
`agentic_runtime_src/agentic_os/kernel/scheduler/`. It is a kernel scheduler
policy for global TaskGraph orchestration above the existing syscall queues.
It does not import ROS2 and does not call bridge clients, Nav2, MoveIt,
provider clients, or skill executors directly.

## Policy

Enable it explicitly with:

```yaml
kernel:
  scheduler_policy: env_aware_priority_dag
```

Accepted aliases are `environment_aware_dag` and `env_aware_priority_dag`.
The default policy remains FIFO for compatibility. The existing
`runtime.scheduler_policy: single_robot_fifo` session-layer setting is not
changed by this kernel policy.

## Runtime Path

Task dispatch uses the existing kernel syscall path:

```text
TaskNode
  -> CapabilityDispatchAdapter
  -> KernelService.execute_request(...)
  -> typed KernelQuery / KernelSyscall
  -> KernelQueueStore lane
  -> RobotCapabilityManager / SkillManager / LLMAdapter / other manager
  -> Runtime permission, access, safety, resource, audit, bridge path
```

The scheduler keeps TaskNode IDs in its ReadyQueue. TaskNodes reference the
AgentControlBlock through `agent_id`; ACB lifecycle and resource handles remain
owned by `AgentLifecycleManager` and `AgentResourceRegistry`.
Before a TaskNode can become ready or running, the scheduler checks
`AgentLifecycleManager.admit_syscall(...)`; lifecycle denials are normalized to
`SCHEDULER_AGENT_NOT_RUNNABLE` with the upstream ACB error in metadata. After
dispatch, the returned KernelSyscall must still carry the same `agent_id`/`aid`
or the node fails before result ingestion.

## Main Components

- `TaskNode`, `TaskGraph`, `TypedEdge`, `GlobalGoalDAG`, and `TaskGraphStore`
  model global DAG state and graph revision.
- `ReadyQueue`, `PriorityKey`, `PriorityScorer`, and critical-path ranking
  select ready TaskNodes without replacing ACBs.
- `EnvironmentFact`, `EnvironmentStore`, and `PreconditionEvaluator` validate
  TTL, confidence, schema, world epoch, and traceable source metadata before
  fact reuse.
- `ResourceArbiter` creates scheduler leases, records them in the ACB resource
  registry, applies TTL expiry, and emits priority inheritance events. The
  dispatch path rechecks selected leases after the capability call returns and
  before result ingestion, so a node that outlives its lease becomes stale with
  `SCHEDULER_RESOURCE_LEASE_EXPIRED` instead of being silently completed.
- `GoalFusionEngine`, `OpportunityIndex`, and `ReuseEdge` propose deterministic
  opportunistic reuse plans. Each plan records a transparent fusion score in
  `audit_metadata`, with route overlap, fact reuse, resource window, deadline
  slack, coverage preservation, user priority, safety risk, coverage loss, and
  resource contention terms. When a `KernelService` is available, accepted
  fusion plans also request a Runtime-owned LLM explanation through
  `KernelService.execute_request(..., LLMQuery(...))`; the returned JSON must
  validate against `fusion_reasoning.schema.json`, and only hash/length/key
  summaries are retained in `audit_metadata`. Rejected plans are audited with
  the same deterministic score evidence. Physical robot/capability fusion
  requires a matched route or workspace `OpportunityWindow`; verified fact reuse
  alone is not enough to claim an opportunistic insertion. A matched window's
  own required preconditions must also validate against real `EnvironmentFact`
  data before the window can be used. The same matched window must also expose
  each requested physical resource ID; otherwise fusion is rejected with
  `SCHEDULER_FUSION_RESOURCE_WINDOW_UNAVAILABLE` instead of treating a score
  penalty as safe. Accepted insertions are materialized as replayable
  precedence edges, including cross-graph dependencies from the
  opportunity-window anchor node to the inserted node and from the inserted node
  to the window's successor when an `end_before_node_id` exists, so ready
  extraction waits on both window boundaries.
- `OnlineGraphReconstructor` handles dynamic graph events with impacted-node
  indexing, deadline reassignment, staged validation, and dirty refresh hooks.
  Deadline reassignment compares the requested dynamic-event budget with the
  impacted critical path before commit; unsatisfiable budgets return
  `SCHEDULER_DEADLINE_UNSATISFIABLE` with required budget and slack metadata.
  `EnvironmentAwareDAGScheduler.apply_dynamic_graph_event(...)` is the live
  service API for applying a `DynamicGraphEvent` to admitted graphs. It stages
  the mutation against the current `TaskGraphStore.revision`, commits only
  validated impacted graphs, replaces each committed graph's opportunity
  windows in `OpportunityIndex`, refreshes ready nodes and dynamic priorities,
  and returns stable structured errors such as
  `SCHEDULER_DYNAMIC_EVENT_INVALID`, `SCHEDULER_GRAPH_NOT_FOUND`, or
  `SCHEDULER_GRAPH_REVISION_CONFLICT`.
  Staging also records reusable fact keys from the real `EnvironmentStore`; it
  does not synthesize facts or call ROS2/provider clients.
- `AdmissionController` rejects graph and node payloads that are not strict
  JSON data before dispatch. TaskNodes cannot carry callables, event loops,
  ROS objects, provider clients, non-string object keys, or non-finite floats in
  open fields such as `params`, `metadata`, or edge metadata. TaskNode
  `resources` are also schema-checked before runtime arbitration: each request
  must name a `resource_id`, use `exclusive` or `shared` mode, carry positive
  `amount` and `lease_ttl_ns`, and use a non-negative `priority_ceiling`.
- Fact creation from traceable capability results emits an
  `environment_fact_created` dynamic event. Fact expiry during scheduler ticks
  emits an `environment_fact_expired` dynamic event, commits impacted graph
  metadata, and revalidates impacted ready nodes before dispatch so stale
  preconditions become structured `scheduler.node.blocked` events instead of
  being dispatched. Declared fact extraction requires explicit evidence for
  the fact value, source audit ID, confidence, and real dependency. Confidence
  may come from a response field or an explicit capability-contract value, but
  it never silently defaults to full confidence; missing confidence returns
  `SCHEDULER_FACT_EXTRACTION_FAILED`, and missing backend/real-dependency
  evidence returns `SCHEDULER_FACT_SOURCE_UNVERIFIED`.
- `SchedulerDebugExporter` emits schema-validated debug snapshots and DOT graph
  exports with sensitive fields redacted. Provider status failures included in
  snapshots keep only exception type plus message hash/length; raw provider,
  prompt, API key, token, or private memory text is not emitted.

## Strict Real-Only Behavior

LLM TaskGraph generation goes through `TaskGraphPlanner`, which calls
`KernelService.execute_request(..., LLMQuery(...))`. If no real provider is
configured, the scheduler returns `SCHEDULER_LLM_REAL_PROVIDER_REQUIRED` with
the upstream provider error. If the Runtime-owned planning syscall path raises
before returning, the planner still returns `SCHEDULER_LLM_REAL_PROVIDER_REQUIRED`
with `SCHEDULER_DISPATCH_FAILED` as the upstream error and only sanitized
exception metadata. It does not synthesize a plan.
LLM TaskNodes use the same `CapabilityDispatchAdapter ->
KernelService.execute_request(..., LLMQuery(...))` path and emit
`scheduler.llm.real_call_started`, `scheduler.llm.real_call_completed`, or
`scheduler.llm.real_call_failed` without storing private prompt text in the
scheduler audit payload.
Fusion-plan explanation uses the same real LLM syscall path with
`operation_type=scheduler_explain_fusion_plan` and schema
`fusion_reasoning.schema.json`. Missing providers return
`SCHEDULER_LLM_REAL_PROVIDER_REQUIRED`; malformed explanation JSON returns
`SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID`. LLM explanation metadata is advisory and
sanitized; deterministic reuse, coverage, resource, safety, and deadline checks
remain the authority for accepting or rejecting fusion.
Every scheduler audit event carries the standard routing envelope
(`agent_id`, `app_id`, `session_id`, `task_graph_id`, `node_id`, `syscall_id`,
`resource_lease_id`, `goal_id`, `success`, and `error_code`) plus
`sanitized_metadata`, a redacted copy of event-specific fields.
Stable `SCHEDULER_*` errors returned or audited by scheduler modules are
registered in `agentic_os.kernel.scheduler.errors.SCHEDULER_ERROR_CODES`,
including generated lifecycle and reuse rejection codes.

Capability dispatch goes through `CapabilityDispatchAdapter`, which creates
typed `RobotCapabilityQuery`, `SkillQuery`, `LLMQuery`, `ToolQuery`,
`MemoryQuery`, `StorageQuery`, or `ContextQuery` objects and submits them to
`KernelService.execute_request`. If a real bridge, provider, backend, or
capability is unavailable, the node fails with a stable structured error. If
`KernelService.execute_request` itself raises, the adapter converts the failure
to `SCHEDULER_DISPATCH_FAILED` and audits only a sanitized exception summary,
not the raw exception text.
The `scheduler.node.dispatched` event is emitted only after the Runtime-owned
kernel path has returned a real `KernelSyscall`, so the event includes the
syscall ID, scheduler revision, queue, target, and resource lease IDs needed for
audit traceability.
DOT graph export reads only scheduler state and redacts sensitive-looking
untrusted graph text in graph IDs, node IDs, agent IDs, capabilities, and fact
labels with stable hash labels instead of emitting raw prompt, key, token, or
private-memory text.
Admission rejects direct robot middleware interfaces in TaskGraphs, including
`nav2.*`, `moveit.*`, `ros2.*`, `/cmd_vel`, `/navigate_to_pose`, Nav2 action
types, MoveIt action types, and velocity/trajectory command markers. Valid
high-level AgenticOS capabilities such as `robot.navigate_to` may still use a
bridge-backed manifest that maps to Nav2 below the Runtime boundary.
When a capability registry is available, admission also verifies protected
robot, perception, arm, gripper, and manipulation TaskNodes have declared
permissions, safety constraints, resource locks for non-read-only actions, and
audit observability after manifest enrichment. Missing contract fields produce
`SCHEDULER_CAPABILITY_CONTRACT_INVALID`.

Checkpointable preemption follows `KernelService.checkpoint_request` and the
runtime SkillExecutor bridge path. The ROS2 bridge contract is
`/agentic/capability/checkpoint` with
`agentic_msgs/srv/CheckpointCapability`. Runtime dispatch carries the kernel
syscall ID as the bridge request ID for inspection, letting checkpoint requests
match only the active capability progress for the same syscall. A bridge
implementation may return `SCHEDULER_PREEMPTION_UNSUPPORTED` when no matching
real active progress exists, but it must not claim checkpoint success without
preserved checkpoint, partial-result, completed-coverage, or progress data.

Fusion commit is two-phase and revision checked. If the global DAG revision
changes after a plan is proposed, commit returns the stable
`SCHEDULER_FUSION_REBASE_REQUIRED` error with the base and current revisions so
the caller can recompute against the latest DAG instead of applying a stale
plan. Accepted reuse edges must also point to a producer TaskNode already
present in the Global DAG; otherwise commit rejects with
`SCHEDULER_FUSION_REUSE_PRODUCER_NOT_IN_DAG` and leaves the graph store
unchanged.

## Cup Reuse Scenario

The scheduler can reuse a real `cup_pose` fact produced during inspection only
when the fact has:

- unexpired TTL
- sufficient confidence
- matching schema and world epoch
- source syscall ID, source audit ID, result hash, source node, source
  capability, and real dependency metadata
- a matched route/workspace `OpportunityWindow` for the physical cup TaskNodes
- matched window resources for the cup TaskNodes, such as the required arm or
  gripper resource IDs

The accepted plan stores both the `ReuseEdge` and precedence dependencies from
the inspection/window anchor to the inserted cup node, and when the inspection
graph has a following node such as `I5`, from the inserted node back to that
successor. The reuse edge can replace repeated perception, but it never marks
`pick_cup`, `verify_cup_held`, or `deliver_cup` complete. Those remain real
capability TaskNodes. Current manifests include color-block manipulation and
inspection capabilities, but generic cup detection, pickup, held verification,
and delivery manifests/backends are not present. The real scheduler capability
verification therefore reports stable unavailable until those real cup
capabilities and bridge/HAL paths are configured.

## Verification

Runtime tests:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
PYTHONPATH=. pytest -q
```

Repository checks:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
scripts/run_tests.sh
scripts/verify_foundation.sh
scripts/verify_capability_truth.sh
scripts/verify_real_llm.sh
scripts/verify_real_scheduler_llm.sh
scripts/verify_real_scheduler_capability.sh
scripts/verify_no_fake_mock.sh
```

The scheduler LLM and capability scripts return
`UNVERIFIED_REAL_DEPENDENCY` with exit code `2` when real dependencies are not
configured. That is an explicit dependency state, not a pass result.
The capability verifier sources the ROS2 setup and the Agentic bridge overlay
from `AGENTIC_ROS2_SETUP` and `AGENTIC_ROS2_BRIDGE_SETUP` when those variables
are set, defaulting to `/opt/ros/humble/setup.bash` and
`/home/ubuntu/agentic_ws/install/setup.bash`. By default it still does not
start or fake a bridge. If the selected capability service/action is absent
from the live ROS graph, it returns `ROS_SERVICE_UNAVAILABLE` or
`ROS_ACTION_UNAVAILABLE` before dispatch. Set
`AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE=1` only to temporarily start the
real read-only state bridge during this verifier run. The preflight uses a
short ROS discovery retry window controlled by
`AGENTIC_VERIFY_ROS_DISCOVERY_ATTEMPTS` and
`AGENTIC_VERIFY_ROS_DISCOVERY_RETRY_DELAY_S`. That preflight
`NEXT_ACTION` includes the required interface name, the number of visible ROS
services/actions, and the exact ROS graph query command, for example
`required=/agentic/robot/get_state`, `visible_services=0`, and
`command=ros2 service list`. For the read-only state bridge service, it also
prints
`start_command=ros2 run agentic_capability_bridge state_bridge_node`,
`bridge_executable=agentic_capability_bridge/state_bridge_node:available`, and
`executable_command=ros2 pkg executables agentic_capability_bridge`, plus
`auto_start_readonly_state_bridge=` when the opt-in start path is used. A
running state bridge without real camera/arm/gripper backend evidence must report
`ROS_BRIDGE_UNAVAILABLE`, with a short bridge reason in `NEXT_ACTION` from the
matching AuditLogger record and a `bridge_missing=` summary when the bridge
returned structured readiness details. It also adds a compact `ros_graph=`
summary with live ROS node/topic/service/action counts and configured
camera/arm/gripper candidate visibility so operators can distinguish a stopped
hardware graph from a profile mismatch. `profile_dependencies=` is derived
from `AGENTIC_VERIFY_BRIDGE_PROFILE_FILE` and summarizes configured camera
launch candidates, `camera_launch_files_present=`, arm topic/service
candidates, action-group file presence, and compact `camera_backend=`,
`arm_backend=`, and `gripper_backend=` status labels. `next_backend_steps=`
contains action labels such as `start_camera_launch` without executing those
hardware backend actions. `backend_step_hints=` translates the labels into
non-executing operator guidance, including profile camera launch selection and
operator-gated arm/servo startup.
When `verify_real_scheduler_llm.sh` does pass, its fusion-reuse setup has also
produced the reused context fact through a scheduler-dispatched real
`ContextQuery` syscall with a real AuditLogger record, not by direct fact
insertion.
When `verify_real_scheduler_capability.sh` does pass, it has also checked that
the scheduler dispatch event, KernelService recent syscall record, acquired
resource lease IDs, and AuditLogger record all reference the same real
capability syscall.
