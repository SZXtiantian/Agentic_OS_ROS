from __future__ import annotations

from agentic_os.kernel.hooks import InMemoryKernelEventSink
from agentic_os.kernel.system_call import KernelResponse
from agentic_os.kernel.system_call import LLMQuery
from agentic_os.kernel.system_call.models import KernelSyscall
from agentic_os.kernel.system_call.executor import SyscallExecutionResult
from agentic_os.kernel.scheduler import CapabilityDispatchAdapter, DispatchLaneMapper, QueryType, ResourceLease, SchedulerAudit, TaskNode


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
