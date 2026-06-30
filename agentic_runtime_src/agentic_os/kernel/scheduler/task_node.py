from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call.models import monotonic_id

from .models import DispatchLaneName, PreemptPolicy, QueryType, TaskNodeStatus, now_ns
from .preconditions import Precondition
from .resources import ResourceRequest


@dataclass
class TaskNode:
    node_id: str
    task_graph_id: str
    user_goal_id: str
    original_goal_id: str
    agent_id: str
    agent_name: str
    app_id: str
    session_id: str
    capability: str
    operation_type: str
    query_type: str
    params: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = TaskNodeStatus.CREATED
    safety_class: str = "normal"
    lane: str = DispatchLaneName.BACKGROUND
    base_priority: int = 0
    inherited_priority: int = 0
    effective_priority: int = 0
    created_ns: int = field(default_factory=now_ns)
    ready_since_ns: int | None = None
    started_ns: int | None = None
    finished_ns: int | None = None
    deadline_ns: int | None = None
    runtime_budget_ns: int | None = None
    estimated_runtime_ns: int | None = None
    period_ns: int | None = None
    dependencies: set[str] = field(default_factory=set)
    dependents: set[str] = field(default_factory=set)
    resources: list[ResourceRequest] = field(default_factory=list)
    preconditions: list[Precondition] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    safety_constraints: dict[str, Any] = field(default_factory=dict)
    input_schema_id: str = ""
    output_schema_id: str = ""
    route_segment_id: str | None = None
    workspace_zone: str | None = None
    produces_facts: list[str] = field(default_factory=list)
    consumes_facts: list[str] = field(default_factory=list)
    reusable_output: bool = False
    opportunistic: bool = False
    fusion_group_id: str | None = None
    preempt_policy: str = PreemptPolicy.NON_PREEMPTIBLE
    syscall_id: str = ""
    syscall_target: str = ""
    syscall_queue_name: str = ""
    resource_lease_ids: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error_code: str = ""
    audit_ids: list[str] = field(default_factory=list)
    critical_path_rank: int = 0

    @classmethod
    def create(
        cls,
        *,
        task_graph_id: str,
        user_goal_id: str,
        agent_id: str,
        agent_name: str,
        app_id: str,
        session_id: str,
        capability: str,
        operation_type: str = "",
        query_type: str = QueryType.SKILL,
        node_id: str = "",
        **kwargs: Any,
    ) -> "TaskNode":
        return cls(
            node_id=node_id or monotonic_id("node"),
            task_graph_id=task_graph_id,
            user_goal_id=user_goal_id,
            original_goal_id=str(kwargs.pop("original_goal_id", user_goal_id)),
            agent_id=agent_id,
            agent_name=agent_name,
            app_id=app_id,
            session_id=session_id,
            capability=capability,
            operation_type=operation_type or capability,
            query_type=query_type,
            **kwargs,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskNode":
        resources = [
            item if isinstance(item, ResourceRequest) else ResourceRequest.from_dict(item)
            for item in list(data.get("resources") or [])
        ]
        preconditions = [
            item if isinstance(item, Precondition) else Precondition.from_dict(item)
            for item in list(data.get("preconditions") or [])
        ]
        dependencies = set(data.get("dependencies") or [])
        dependents = set(data.get("dependents") or [])
        return cls(
            node_id=str(data.get("node_id") or data.get("id") or monotonic_id("node")),
            task_graph_id=str(data.get("task_graph_id") or ""),
            user_goal_id=str(data.get("user_goal_id") or ""),
            original_goal_id=str(data.get("original_goal_id") or data.get("user_goal_id") or ""),
            agent_id=str(data.get("agent_id") or ""),
            agent_name=str(data.get("agent_name") or data.get("app_id") or ""),
            app_id=str(data.get("app_id") or ""),
            session_id=str(data.get("session_id") or ""),
            capability=str(data.get("capability") or data.get("skill_name") or ""),
            operation_type=str(data.get("operation_type") or data.get("capability") or data.get("skill_name") or ""),
            query_type=str(data.get("query_type") or QueryType.SKILL),
            params=dict(data.get("params") or {}),
            metadata=dict(data.get("metadata") or {}),
            status=str(data.get("status") or TaskNodeStatus.CREATED),
            safety_class=str(data.get("safety_class") or "normal"),
            lane=str(data.get("lane") or DispatchLaneName.BACKGROUND),
            base_priority=int(data.get("base_priority", 0)),
            inherited_priority=int(data.get("inherited_priority", 0)),
            effective_priority=int(data.get("effective_priority", 0)),
            created_ns=int(data.get("created_ns", now_ns())),
            ready_since_ns=data.get("ready_since_ns"),
            started_ns=data.get("started_ns"),
            finished_ns=data.get("finished_ns"),
            deadline_ns=data.get("deadline_ns"),
            runtime_budget_ns=data.get("runtime_budget_ns"),
            estimated_runtime_ns=data.get("estimated_runtime_ns"),
            period_ns=data.get("period_ns"),
            dependencies=dependencies,
            dependents=dependents,
            resources=resources,
            preconditions=preconditions,
            required_permissions=list(data.get("required_permissions") or []),
            safety_constraints=dict(data.get("safety_constraints") or {}),
            input_schema_id=str(data.get("input_schema_id") or ""),
            output_schema_id=str(data.get("output_schema_id") or ""),
            route_segment_id=data.get("route_segment_id"),
            workspace_zone=data.get("workspace_zone"),
            produces_facts=list(data.get("produces_facts") or []),
            consumes_facts=list(data.get("consumes_facts") or []),
            reusable_output=bool(data.get("reusable_output", False)),
            opportunistic=bool(data.get("opportunistic", False)),
            fusion_group_id=data.get("fusion_group_id"),
            preempt_policy=str(data.get("preempt_policy") or PreemptPolicy.NON_PREEMPTIBLE),
            syscall_id=str(data.get("syscall_id") or ""),
            syscall_target=str(data.get("syscall_target") or ""),
            syscall_queue_name=str(data.get("syscall_queue_name") or ""),
            resource_lease_ids=list(data.get("resource_lease_ids") or []),
            result=data.get("result"),
            error_code=str(data.get("error_code") or ""),
            audit_ids=list(data.get("audit_ids") or []),
            critical_path_rank=int(data.get("critical_path_rank", 0)),
        )

    def mark_status(self, status: str, *, error_code: str = "") -> None:
        self.status = status
        if status == TaskNodeStatus.READY:
            self.ready_since_ns = self.ready_since_ns or now_ns()
        if status in {TaskNodeStatus.DISPATCHING, TaskNodeStatus.RUNNING}:
            self.started_ns = self.started_ns or now_ns()
        if status in TaskNodeStatus.TERMINAL:
            self.finished_ns = self.finished_ns or now_ns()
        if error_code:
            self.error_code = error_code
        elif status not in {TaskNodeStatus.BLOCKED, TaskNodeStatus.FAILED, TaskNodeStatus.CANCELLED, TaskNodeStatus.STALE, TaskNodeStatus.REJECTED}:
            self.error_code = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["dependencies"] = sorted(self.dependencies)
        data["dependents"] = sorted(self.dependents)
        data["resources"] = [resource.to_dict() for resource in self.resources]
        data["preconditions"] = [precondition.to_dict() for precondition in self.preconditions]
        return data


def produced_fact_keys_for_node(node: TaskNode) -> list[str]:
    facts = list(node.produces_facts)
    facts.extend(_fact_keys_from_specs(node.metadata.get("produces_fact_specs")))
    return _unique_nonempty(facts)


def consumed_fact_keys_for_node(node: TaskNode) -> list[str]:
    facts = list(node.consumes_facts)
    facts.extend(_fact_keys_from_specs(node.metadata.get("consumes_fact_specs")))
    for precondition in node.preconditions:
        facts.append(precondition.fact_key)
    return _unique_nonempty(facts)


def fact_keys_for_node(node: TaskNode) -> list[str]:
    return _unique_nonempty([*produced_fact_keys_for_node(node), *consumed_fact_keys_for_node(node)])


def _fact_keys_from_specs(specs: Any) -> list[str]:
    if not isinstance(specs, list):
        return []
    keys: list[str] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        keys.append(str(spec.get("fact_key") or spec.get("key") or ""))
    return keys


def _unique_nonempty(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "")
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result
