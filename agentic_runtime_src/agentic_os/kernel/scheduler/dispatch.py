from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_os.kernel.hooks import KernelQueueName
from agentic_os.kernel.system_call import ContextQuery, KernelQuery, LLMQuery, MemoryQuery, RobotCapabilityQuery, SkillQuery, StorageQuery, ToolQuery

from .audit import SchedulerAudit
from .errors import SchedulerResult
from .models import DispatchLaneName, QueryType, stable_hash_payload
from .resources import ResourceLease
from .task_node import TaskNode


DEFAULT_DAG_DISPATCH_LANES = {
    DispatchLaneName.EMERGENCY: KernelQueueName.ROBOT_MOTION,
    DispatchLaneName.SAFETY: KernelQueueName.ROBOT_SENSOR,
    DispatchLaneName.MOTION: KernelQueueName.ROBOT_MOTION,
    DispatchLaneName.PERCEPTION: KernelQueueName.ROBOT_SENSOR,
    DispatchLaneName.LLM_TOOL: KernelQueueName.LLM,
    DispatchLaneName.IO_AUDIT: KernelQueueName.STORAGE,
    DispatchLaneName.BACKGROUND: KernelQueueName.CONTEXT,
}


class DispatchLaneMapper:
    def derive_lane(self, node: TaskNode) -> str:
        capability = node.capability.lower()
        safety_class = node.safety_class.lower()
        if capability in {"robot.stop", "emergency_stop"}:
            return DispatchLaneName.EMERGENCY
        if safety_class == "emergency":
            return DispatchLaneName.SAFETY
        if safety_class in {"safety", "safety_monitor", "human_safety", "collision_risk"}:
            return DispatchLaneName.SAFETY
        if node.query_type == QueryType.LLM:
            return DispatchLaneName.LLM_TOOL
        if node.query_type in {QueryType.MEMORY, QueryType.STORAGE, QueryType.CONTEXT}:
            return DispatchLaneName.BACKGROUND if node.query_type == QueryType.CONTEXT else DispatchLaneName.IO_AUDIT
        if node.query_type == QueryType.TOOL:
            return DispatchLaneName.LLM_TOOL
        if capability.startswith(("robot.navigate_to", "arm.", "gripper.", "manipulation.")):
            return DispatchLaneName.MOTION
        if capability.startswith(("perception.", "robot.get_state", "robot.inspect_area")):
            return DispatchLaneName.PERCEPTION
        if capability.startswith("human."):
            return DispatchLaneName.SAFETY
        return node.lane or DispatchLaneName.BACKGROUND

    def queue_name_for(self, node: TaskNode) -> str:
        lane = self.derive_lane(node)
        return DEFAULT_DAG_DISPATCH_LANES.get(lane, KernelQueueName.CONTEXT)


@dataclass
class DispatchResult:
    success: bool
    error_code: str = ""
    syscall_id: str = ""
    syscall_agent_id: str = ""
    response: Any = None
    metadata: dict[str, Any] | None = None


class CapabilityDispatchAdapter:
    def __init__(self, *, kernel_service: Any, lane_mapper: DispatchLaneMapper | None = None, audit: SchedulerAudit | None = None) -> None:
        self.kernel_service = kernel_service
        self.lane_mapper = lane_mapper or DispatchLaneMapper()
        self.audit = audit or SchedulerAudit()

    def dispatch(self, node: TaskNode, leases: list[ResourceLease], *, scheduler_revision: int, timeout_s: float | None = None) -> DispatchResult:
        try:
            query = self._query_from_node(node, leases=leases, scheduler_revision=scheduler_revision)
        except ValueError as exc:
            return DispatchResult(False, error_code=str(exc) or "SCHEDULER_LANE_UNSUPPORTED")
        if node.query_type == QueryType.LLM:
            self.audit.emit(
                "scheduler.llm.real_call_started",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                operation_type=query.operation_type,
                action_type=getattr(query, "action_type", ""),
                schema_id=node.output_schema_id or str(node.params.get("schema_id") or ""),
                success=True,
            )
        try:
            result = self.kernel_service.execute_request(node.agent_name or node.app_id, query, timeout_s=timeout_s)
        except Exception as exc:
            metadata = {"exception": _exception_summary(exc)}
            if node.query_type == QueryType.LLM:
                self.audit.emit(
                    "scheduler.llm.real_call_failed",
                    success=False,
                    error_code="SCHEDULER_DISPATCH_FAILED",
                    agent_id=node.agent_id,
                    app_id=node.app_id,
                    session_id=node.session_id,
                    task_graph_id=node.task_graph_id,
                    node_id=node.node_id,
                    operation_type=query.operation_type,
                    action_type=getattr(query, "action_type", ""),
                    schema_id=node.output_schema_id or str(node.params.get("schema_id") or ""),
                    upstream_error_code="SCHEDULER_DISPATCH_FAILED",
                    **metadata,
                )
            return DispatchResult(False, error_code="SCHEDULER_DISPATCH_FAILED", metadata=metadata)
        node.syscall_id = result.syscall.syscall_id
        node.syscall_queue_name = str(result.metadata.get("queue_name") or getattr(result.syscall, "queue_name", ""))
        node.syscall_target = result.syscall.target
        self.audit.emit(
            "scheduler.node.dispatched",
            agent_id=node.agent_id,
            app_id=node.app_id,
            session_id=node.session_id,
            task_graph_id=node.task_graph_id,
            node_id=node.node_id,
            syscall_id=result.syscall.syscall_id,
            resource_lease_id=",".join(lease.lease_id for lease in leases),
            scheduler_revision=scheduler_revision,
            syscall_target=node.syscall_target,
            queue_name=node.syscall_queue_name,
            success=True,
        )
        if result.success:
            if node.query_type == QueryType.LLM:
                self.audit.emit(
                    "scheduler.llm.real_call_completed",
                    agent_id=node.agent_id,
                    app_id=node.app_id,
                    session_id=node.session_id,
                    task_graph_id=node.task_graph_id,
                    node_id=node.node_id,
                    syscall_id=result.syscall.syscall_id,
                    operation_type=query.operation_type,
                    action_type=getattr(query, "action_type", ""),
                    schema_id=node.output_schema_id or str(node.params.get("schema_id") or ""),
                    model=str(result.metadata.get("model") or ""),
                    queue_name=node.syscall_queue_name,
                    success=True,
                )
            return DispatchResult(
                True,
                syscall_id=result.syscall.syscall_id,
                syscall_agent_id=_syscall_agent_id(result.syscall),
                response=result.response,
                metadata=dict(result.metadata),
            )
        if node.query_type == QueryType.LLM:
            error_code = result.error_code or "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED"
            self.audit.emit(
                "scheduler.llm.real_call_failed",
                success=False,
                error_code=error_code,
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                syscall_id=result.syscall.syscall_id,
                operation_type=query.operation_type,
                action_type=getattr(query, "action_type", ""),
                schema_id=node.output_schema_id or str(node.params.get("schema_id") or ""),
                upstream_error_code=result.error_code,
                queue_name=node.syscall_queue_name,
            )
        return DispatchResult(
            False,
            error_code=result.error_code or "SCHEDULER_DISPATCH_FAILED",
            syscall_id=result.syscall.syscall_id,
            syscall_agent_id=_syscall_agent_id(result.syscall),
            response=result.response,
            metadata=dict(result.metadata),
        )

    def _query_from_node(self, node: TaskNode, *, leases: list[ResourceLease], scheduler_revision: int) -> KernelQuery:
        metadata = {
            **dict(node.metadata),
            "agent_id": node.agent_id,
            "app_id": node.app_id,
            "session_id": node.session_id,
            "permissions": list(node.required_permissions),
            "task_graph_id": node.task_graph_id,
            "node_id": node.node_id,
            "scheduler_revision": scheduler_revision,
            "resource_lease_ids": [lease.lease_id for lease in leases],
            "scheduler_component": "environment_aware_dag",
        }
        params = dict(node.params)
        if node.query_type == QueryType.LLM:
            return LLMQuery(
                operation_type=node.operation_type,
                params=params,
                messages=list(params.get("messages") or []),
                tools=params.get("tools"),
                selected_llms=params.get("selected_llms"),
                response_format=params.get("response_format"),
                action_type=str(params.get("action_type") or node.operation_type),
                metadata=metadata,
            )
        if node.query_type == QueryType.ROBOT_CAPABILITY:
            return RobotCapabilityQuery(
                operation_type=node.operation_type or node.capability,
                params=params,
                skill_name=node.capability,
                app_id=node.app_id,
                session_id=node.session_id,
                metadata=metadata,
            )
        if node.query_type in {QueryType.SKILL, QueryType.HUMAN}:
            return SkillQuery(
                operation_type=node.operation_type or "skill_call",
                params=params,
                skill_name=node.capability,
                call_id=params.get("call_id", ""),
                app_id=node.app_id,
                session_id=node.session_id,
                metadata=metadata,
            )
        if node.query_type == QueryType.TOOL:
            return ToolQuery(operation_type=node.operation_type, params=params, tool_calls=list(params.get("tool_calls") or []), metadata=metadata)
        if node.query_type == QueryType.MEMORY:
            return MemoryQuery(operation_type=node.operation_type, params=params, metadata=metadata)
        if node.query_type == QueryType.STORAGE:
            return StorageQuery(operation_type=node.operation_type, params=params, metadata=metadata)
        if node.query_type == QueryType.CONTEXT:
            return ContextQuery(
                operation_type=node.operation_type,
                params=params,
                namespace=str(params.get("namespace") or "context"),
                session_id=node.session_id,
                checkpoint=str(params.get("checkpoint") or ""),
                metadata=metadata,
            )
        raise ValueError("SCHEDULER_LANE_UNSUPPORTED")


def _syscall_agent_id(syscall: Any) -> str:
    return str(getattr(syscall, "agent_id", "") or getattr(syscall, "aid", "") or "")


def _exception_summary(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    return {
        "type": type(exc).__name__,
        "message_sha256": stable_hash_payload(message),
        "message_length": len(message),
    }
