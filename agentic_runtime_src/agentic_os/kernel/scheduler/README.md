# Scheduler

The scheduler package contains two layers:

- Legacy `FIFORequestScheduler` and `RoundRobinRequestScheduler`, kept for existing runtime wrappers.
- Kernel scheduler v2, where `FIFOKernelScheduler` starts module processing threads that consume named kernel queues and call each manager's `address_request(syscall)`.
- `EnvironmentAwareDAGScheduler`, enabled explicitly with
  `kernel.scheduler_policy: env_aware_priority_dag`, adds global TaskGraph
  scheduling, environment facts, priority scoring, resource leases, lifecycle
  hooks, fusion/reuse planning, dynamic graph event reconstruction, debug
  snapshots, and DOT export.

Robot motion uses a dedicated non-preemptible `robot_motion` lane with one worker by default. Generic tools stay on the `tool` lane and must not expose robot capabilities.

Contract module for AgenticOS scheduling and session execution.

The DAG scheduler dispatch adapter creates typed KernelQuery objects and calls
`KernelService.execute_request(...)`. It does not call SkillExecutor,
SkillDispatcher, bridge clients, ROS2 APIs, Nav2, MoveIt, or LLM provider
clients directly. Exceptions from `execute_request` are returned as
`SCHEDULER_DISPATCH_FAILED` with sanitized exception summaries instead of raw
provider or prompt text.
`scheduler.node.dispatched` is emitted after the Runtime-owned syscall is
created, and carries the real syscall ID, queue, target, scheduler revision, and
resource lease IDs for traceability.
DOT export keeps graph structure visible while replacing sensitive-looking
untrusted labels with stable redacted hash labels.
LLM TaskNodes emit scheduler real-call audit lifecycle events around that
Runtime-owned LLM query path without storing prompt text.
Accepted fusion plans can request a Runtime-owned LLM explanation through the
same syscall path. The result must validate against
`fusion_reasoning.schema.json`; only sanitized summaries are stored, and the
LLM explanation never replaces deterministic reuse, coverage, resource, safety,
or deadline checks.

Admission rejects direct ROS2/Nav2/MoveIt interface labels in TaskNodes. Use
high-level AgenticOS capabilities such as `robot.navigate_to`; the manifest and
bridge layer own any lower-level Nav2 or MoveIt mapping.
With a runtime capability registry, admission also requires protected robot,
perception, arm, gripper, and manipulation nodes to have permissions, safety
constraints, resource locks for non-read-only actions, and audit observability.
Resource requests are schema-checked before arbitration, including lock mode,
positive lease TTL, positive amount, and non-negative priority ceiling.

Dynamic graph adaptation is exposed through
`EnvironmentAwareDAGScheduler.apply_dynamic_graph_event(...)`. The API accepts
a `DynamicGraphEvent`, stages the mutation through `OnlineGraphReconstructor`,
commits validated impacted graphs against the current graph-store revision, and
then refreshes ready nodes and dynamic priorities. Invalid events and stale
graph references return structured scheduler errors; no real dependency is
faked or called by this path.

Traceable environment fact creation and fact expiry also feed this same path:
created facts emit `environment_fact_created`, expired facts emit
`environment_fact_expired`, and impacted ready nodes are rechecked before
dispatch.
