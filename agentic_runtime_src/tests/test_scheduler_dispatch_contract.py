from __future__ import annotations

import ast

import pytest

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.system_call import (
    ContextQuery,
    KernelQuery,
    KernelResponse,
    LLMQuery,
    MemoryQuery,
    RobotCapabilityQuery,
    SkillQuery,
    StorageQuery,
    ToolQuery,
)
from agentic_os.kernel.system_call.models import KernelSyscall
from agentic_os.kernel.system_call.executor import SyscallExecutionResult
from agentic_os.kernel.scheduler import (
    CapabilityDispatchAdapter,
    DispatchLaneMapper,
    EnvironmentAwareDAGScheduler,
    QueryType,
    ResourceLease,
    SchedulerAudit,
    TaskGraph,
    TaskNode,
)


class RecordingKernelService:
    def __init__(self) -> None:
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        syscall = KernelSyscall.create(agent_name, "skill", query.operation_type, query.params)
        syscall.syscall_id = "ksc_real_dispatch"
        syscall.target = "skill"
        return SyscallExecutionResult(
            syscall=syscall,
            response=KernelResponse.ok({"ok": True}, metadata={"audit_id": "audit_real"}, data={"ok": True}),
            success=True,
            metadata={"queue_name": "skill", "audit_id": "audit_real"},
        )


class RaisingKernelService:
    def __init__(self) -> None:
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        raise RuntimeError("api_key=secret-value prompt=private user instruction")


def test_dispatch_adapter_uses_kernel_service_execute_request():
    service = RecordingKernelService()
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "ready"},
    )

    result = CapabilityDispatchAdapter(kernel_service=service).dispatch(node, [], scheduler_revision=7)

    assert result.success is True
    assert service.calls[0][0] == "app"
    assert service.calls[0][1].metadata["node_id"] == "n"
    assert service.calls[0][1].metadata["scheduler_revision"] == 7


@pytest.mark.parametrize(
    ("query_type", "capability", "operation_type", "params", "expected_query_cls"),
    [
        (QueryType.LLM, "llm.plan", "llm.reason", {"messages": [], "response_format": {"type": "json_object"}}, LLMQuery),
        (QueryType.ROBOT_CAPABILITY, "robot.get_state", "robot.get_state", {}, RobotCapabilityQuery),
        (QueryType.SKILL, "report.say", "skill_call", {"message": "ready"}, SkillQuery),
        (QueryType.HUMAN, "human.ask", "skill_call", {"question": "Continue?"}, SkillQuery),
        (QueryType.TOOL, "tool.search", "tool_call", {"tool_calls": [{"name": "status", "arguments": {}}]}, ToolQuery),
        (QueryType.MEMORY, "memory.recall", "mem_recall", {"key": "k"}, MemoryQuery),
        (QueryType.STORAGE, "storage.list", "sto_list", {"prefix": "photos/"}, StorageQuery),
        (QueryType.CONTEXT, "context.get", "ctx_get", {"namespace": "ns", "key": "k"}, ContextQuery),
    ],
)
def test_dispatch_adapter_builds_typed_kernel_query_for_each_scheduler_query_type(
    query_type,
    capability,
    operation_type,
    params,
    expected_query_cls,
):
    service = RecordingKernelService()
    node = TaskNode.create(
        node_id=f"node_{query_type}",
        task_graph_id="g_typed_query",
        user_goal_id="goal_typed_query",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability=capability,
        operation_type=operation_type,
        query_type=query_type,
        params=params,
        required_permissions=["perm.required"],
    )

    result = CapabilityDispatchAdapter(kernel_service=service).dispatch(node, [], scheduler_revision=7)

    assert result.success is True
    query = service.calls[0][1]
    assert isinstance(query, expected_query_cls)
    assert isinstance(query, KernelQuery)
    assert query.operation_type == operation_type
    assert query.params == params
    assert query.metadata["agent_id"] == "agent"
    assert query.metadata["app_id"] == "app"
    assert query.metadata["session_id"] == "sess"
    assert query.metadata["task_graph_id"] == "g_typed_query"
    assert query.metadata["node_id"] == f"node_{query_type}"
    assert query.metadata["scheduler_revision"] == 7
    assert query.metadata["permissions"] == ["perm.required"]
    assert query.metadata["scheduler_component"] == "environment_aware_dag"


def test_dispatch_adapter_audits_unsupported_query_type_without_kernel_call():
    sink = InMemoryKernelEventSink()
    service = RecordingKernelService()
    node = TaskNode.create(
        node_id="bad_query",
        task_graph_id="g_bad_query",
        user_goal_id="goal_bad_query",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="unsupported.capability",
        operation_type="unsupported.operation",
        query_type="unsupported_query_type",
        params={"api_key": "secret-value"},
    )

    result = CapabilityDispatchAdapter(kernel_service=service, audit=SchedulerAudit(event_sink=sink)).dispatch(
        node,
        [],
        scheduler_revision=7,
    )
    events = sink.recent(limit=20)
    events_text = str(events)

    assert result.success is False
    assert result.error_code == "SCHEDULER_LANE_UNSUPPORTED"
    assert result.metadata == {"query_type": "unsupported_query_type"}
    assert service.calls == []
    assert "secret-value" not in events_text
    assert any(
        event["event_type"] == "scheduler.node.failed"
        and event["metadata"]["node_id"] == "bad_query"
        and event["metadata"]["goal_id"] == "goal_bad_query"
        and event["metadata"]["scheduler_revision"] == 7
        and event["metadata"]["query_type"] == "unsupported_query_type"
        and event["metadata"]["error_code"] == "SCHEDULER_LANE_UNSUPPORTED"
        for event in events
    )


def test_scheduler_dispatch_boundary_has_no_direct_runtime_or_bridge_clients(runtime_src):
    scheduler_root = runtime_src / "agentic_os" / "kernel" / "scheduler"
    forbidden_import_roots = {
        "agentic_runtime.skill_executor",
        "agentic_runtime.ros_bridge_client",
        "agentic_os.kernel.llm_core",
        "rclpy",
    }
    forbidden_source_tokens = {
        "SkillExecutor",
        "SkillDispatcher",
        "Ros2CliBridgeClient",
        "create_ros_bridge_client",
        "bridge_client.",
    }
    violations: list[str] = []
    for path in scheduler_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == root or alias.name.startswith(f"{root}.") for root in forbidden_import_roots):
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if any(module == root or module.startswith(f"{root}.") for root in forbidden_import_roots):
                    violations.append(f"{path.name}: from {module} import ...")
        for token in forbidden_source_tokens:
            if token in source:
                violations.append(f"{path.name}: {token}")

    dispatch_source = (scheduler_root / "dispatch.py").read_text(encoding="utf-8")

    assert violations == []
    assert ".execute_request(" in dispatch_source


def test_dispatch_adapter_audits_dispatched_node_with_real_syscall_and_lease_trace():
    sink = InMemoryKernelEventSink()
    service = RecordingKernelService()
    node = TaskNode.create(
        node_id="n_trace",
        task_graph_id="g_trace",
        user_goal_id="goal_trace",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "ready"},
    )
    lease = ResourceLease.create(
        resource_id="speaker",
        holder_node_id=node.node_id,
        holder_agent_id=node.agent_id,
        mode="exclusive",
        acquired_ns=1,
        lease_ttl_ns=100_000_000,
        holder_base_priority=node.base_priority,
    )

    result = CapabilityDispatchAdapter(kernel_service=service, audit=SchedulerAudit(event_sink=sink)).dispatch(
        node,
        [lease],
        scheduler_revision=7,
    )
    events = sink.recent(limit=20)

    assert result.success is True
    dispatched = [event for event in events if event["event_type"] == "scheduler.node.dispatched"]
    assert len(dispatched) == 1
    metadata = dispatched[0]["metadata"]
    assert metadata["syscall_id"] == "ksc_real_dispatch"
    assert metadata["resource_lease_id"] == lease.lease_id
    assert metadata["scheduler_revision"] == 7
    assert metadata["syscall_target"] == "skill"
    assert metadata["queue_name"] == "skill"
    assert metadata["sanitized_metadata"]["scheduler_revision"] == 7


def test_dispatch_adapter_returns_stable_error_when_kernel_service_raises_without_leaking_exception_text():
    sink = InMemoryKernelEventSink()
    service = RaisingKernelService()
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "ready"},
    )

    result = CapabilityDispatchAdapter(kernel_service=service, audit=SchedulerAudit(event_sink=sink)).dispatch(node, [], scheduler_revision=7)
    events_text = str(sink.recent(limit=20))

    assert result.success is False
    assert result.error_code == "SCHEDULER_DISPATCH_FAILED"
    assert result.metadata["exception"]["type"] == "RuntimeError"
    assert set(result.metadata["exception"]) == {"type", "message_sha256", "message_length"}
    assert service.calls[0][1].metadata["node_id"] == "n"
    assert "secret-value" not in str(result.metadata)
    assert "private user instruction" not in str(result.metadata)
    assert "secret-value" not in events_text
    assert "private user instruction" not in events_text
    assert not any(event["event_type"] == "scheduler.node.dispatched" for event in sink.recent(limit=20))


def test_scheduler_tick_marks_dispatch_exception_failed_and_audits_without_sensitive_text():
    sink = InMemoryKernelEventSink()
    service = RaisingKernelService()
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(event_sink=sink),
        {},
        kernel_service=service,
        event_sink=sink,
    )
    node = TaskNode.create(
        node_id="dispatch_raises",
        task_graph_id="g_dispatch_raises",
        user_goal_id="goal_dispatch_raises",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "ready"},
    )
    graph = TaskGraph.create(
        task_graph_id="g_dispatch_raises",
        user_goal_id="goal_dispatch_raises",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={node.node_id: node},
    )

    submit = scheduler.submit_graph(graph)
    decisions = scheduler.tick(max_dispatch=1)
    events = sink.recent(limit=50)
    events_text = str(events)
    stored_node = scheduler.graph_store.get_node(node.node_id)

    assert submit.success is True
    assert decisions == [{"node_id": "dispatch_raises", "success": False, "error_code": "SCHEDULER_DISPATCH_FAILED", "syscall_id": ""}]
    assert stored_node.status == "failed"
    assert stored_node.error_code == "SCHEDULER_DISPATCH_FAILED"
    assert "secret-value" not in events_text
    assert "private user instruction" not in events_text
    assert any(
        event["event_type"] == "scheduler.node.failed"
        and event["metadata"]["node_id"] == "dispatch_raises"
        and event["metadata"]["error_code"] == "SCHEDULER_DISPATCH_FAILED"
        and event["metadata"]["syscall_id"] == ""
        for event in events
    )


class LLMKernelService:
    def __init__(self, *, success: bool = True, error_code: str = "") -> None:
        self.success = success
        self.error_code = error_code
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        syscall = KernelSyscall.create(agent_name, "llm", query.operation_type, query.params)
        syscall.syscall_id = "ksc_real_llm_node"
        syscall.target = "llm"
        response = KernelResponse.ok({"content": "{}"}, metadata={"audit_id": "audit_llm"}, data={"content": "{}"})
        return SyscallExecutionResult(
            syscall=syscall,
            response=response if self.success else KernelResponse.error(self.error_code, metadata={"audit_id": "audit_llm"}),
            success=self.success,
            error_code=self.error_code,
            metadata={"queue_name": "llm", "audit_id": "audit_llm", "model": "real-model"},
        )


def _llm_node() -> TaskNode:
    return TaskNode.create(
        node_id="llm_node",
        task_graph_id="g_llm_node",
        user_goal_id="goal_llm_node",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="llm.plan",
        operation_type="llm.reason",
        query_type=QueryType.LLM,
        params={
            "messages": [{"role": "user", "content": "private prompt text"}],
            "action_type": "scheduler_llm_task",
            "schema_id": "llm_node.schema.json",
            "response_format": {"type": "json_object"},
        },
        output_schema_id="llm_node.schema.json",
    )


def test_dispatch_adapter_audits_llm_tasknode_real_call_lifecycle_without_prompt_text():
    sink = InMemoryKernelEventSink()
    service = LLMKernelService(success=True)
    node = _llm_node()

    result = CapabilityDispatchAdapter(kernel_service=service, audit=SchedulerAudit(event_sink=sink)).dispatch(node, [], scheduler_revision=7)
    events = sink.recent(limit=20)

    assert result.success is True
    assert isinstance(service.calls[0][1], LLMQuery)
    assert "private prompt text" not in str(events)
    assert any(
        event["event_type"] == "scheduler.llm.real_call_started"
        and event["metadata"]["node_id"] == "llm_node"
        and event["metadata"]["schema_id"] == "llm_node.schema.json"
        for event in events
    )
    assert any(
        event["event_type"] == "scheduler.llm.real_call_completed"
        and event["metadata"]["syscall_id"] == "ksc_real_llm_node"
        and event["metadata"]["model"] == "real-model"
        for event in events
    )


def test_dispatch_adapter_audits_llm_tasknode_real_call_failure():
    sink = InMemoryKernelEventSink()
    service = LLMKernelService(success=False, error_code="LLM_PROVIDER_UNCONFIGURED")
    node = _llm_node()

    result = CapabilityDispatchAdapter(kernel_service=service, audit=SchedulerAudit(event_sink=sink)).dispatch(node, [], scheduler_revision=7)
    events = sink.recent(limit=20)

    assert result.success is False
    assert result.error_code == "LLM_PROVIDER_UNCONFIGURED"
    assert any(event["event_type"] == "scheduler.llm.real_call_started" for event in events)
    assert any(
        event["event_type"] == "scheduler.llm.real_call_failed"
        and event["metadata"]["error_code"] == "LLM_PROVIDER_UNCONFIGURED"
        and event["metadata"]["upstream_error_code"] == "LLM_PROVIDER_UNCONFIGURED"
        and event["metadata"]["syscall_id"] == "ksc_real_llm_node"
        for event in events
    )


def test_dispatch_adapter_audits_llm_tasknode_execute_request_exception_as_stable_failure():
    sink = InMemoryKernelEventSink()
    service = RaisingKernelService()
    node = _llm_node()

    result = CapabilityDispatchAdapter(kernel_service=service, audit=SchedulerAudit(event_sink=sink)).dispatch(node, [], scheduler_revision=7)
    events = sink.recent(limit=20)
    events_text = str(events)

    assert result.success is False
    assert result.error_code == "SCHEDULER_DISPATCH_FAILED"
    assert "secret-value" not in events_text
    assert "private user instruction" not in events_text
    assert any(event["event_type"] == "scheduler.llm.real_call_started" for event in events)
    assert any(
        event["event_type"] == "scheduler.llm.real_call_failed"
        and event["metadata"]["error_code"] == "SCHEDULER_DISPATCH_FAILED"
        and event["metadata"]["upstream_error_code"] == "SCHEDULER_DISPATCH_FAILED"
        and event["metadata"]["exception"]["type"] == "RuntimeError"
        for event in events
    )


def test_dispatch_lane_mapper_derives_emergency_from_stop_capability_not_motion_label():
    mapper = DispatchLaneMapper()
    navigate = TaskNode.create(
        node_id="nav",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        safety_class="emergency",
    )
    stop = TaskNode.create(
        node_id="stop",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.stop",
        operation_type="robot.stop",
        query_type=QueryType.ROBOT_CAPABILITY,
        safety_class="emergency",
    )

    assert mapper.derive_lane(navigate) == "safety"
    assert mapper.derive_lane(stop) == "emergency"
