from __future__ import annotations

from agentic_os.kernel.hooks import InMemoryKernelEventSink
from agentic_os.kernel.scheduler import PreemptPolicy, QueryType, SchedulerAudit, TaskNode
from agentic_os.kernel.scheduler.preemption import PreemptionManager
from agentic_os.kernel.system_call import KernelResponse, RobotCapabilityQuery
from agentic_os.kernel.system_call.executor import SyscallExecutionResult
from agentic_os.kernel.system_call.models import KernelSyscall


class RecordingKernelService:
    def __init__(self) -> None:
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        syscall = KernelSyscall.create(agent_name, "robot_motion", query.operation_type, query.params)
        syscall.syscall_id = "ksc_emergency_stop"
        syscall.target = "robot_motion"
        return SyscallExecutionResult(
            syscall=syscall,
            response=KernelResponse.ok({"accepted": True}, metadata={"audit_id": "audit_stop"}, data={"accepted": True}),
            success=True,
            metadata={"queue_name": "robot_motion", "audit_id": "audit_stop"},
        )


def _motion_node() -> TaskNode:
    return TaskNode.create(
        node_id="move",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        preempt_policy=PreemptPolicy.EMERGENCY_STOP_ONLY,
        syscall_id="ksc_motion",
        required_permissions=["robot.stop"],
    )


def _inspection_node() -> TaskNode:
    return TaskNode.create(
        node_id="inspect",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        operation_type="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        preempt_policy=PreemptPolicy.CHECKPOINTABLE,
        syscall_id="ksc_inspection",
    )


def test_emergency_stop_only_preemption_dispatches_robot_stop_through_kernel_service():
    sink = InMemoryKernelEventSink()
    service = RecordingKernelService()
    manager = PreemptionManager(kernel_service=service, audit=SchedulerAudit(event_sink=sink))

    result = manager.request_preemption(_motion_node(), reason="safety_interrupt")

    assert result.success is True
    assert result.metadata["emergency_stop_syscall_id"] == "ksc_emergency_stop"
    assert len(service.calls) == 1
    agent_name, query, timeout_s = service.calls[0]
    assert agent_name == "app"
    assert isinstance(query, RobotCapabilityQuery)
    assert query.skill_name == "robot.stop"
    assert query.operation_type == "robot.stop"
    assert query.params["preempted_syscall_id"] == "ksc_motion"
    assert query.metadata["node_id"] == "move"
    assert query.metadata["permissions"] == ["robot.stop"]
    assert timeout_s == 5.0
    event_types = [event["event_type"] for event in sink.recent(limit=20)]
    assert "scheduler.safety.interrupt" in event_types
    assert "scheduler.preemption.accepted" in event_types
    accepted = [event for event in sink.recent(limit=20) if event["event_type"] == "scheduler.preemption.accepted"][-1]
    assert accepted["metadata"]["app_id"] == "app"
    assert accepted["metadata"]["session_id"] == "sess"
    assert accepted["metadata"]["task_graph_id"] == "g"
    assert accepted["metadata"]["syscall_id"] == "ksc_motion"
    assert accepted["metadata"]["goal_id"] == "goal"


def test_emergency_stop_only_preemption_rejects_non_emergency_reason():
    service = RecordingKernelService()
    manager = PreemptionManager(kernel_service=service)

    result = manager.request_preemption(_motion_node(), reason="operator_suspend")

    assert result.success is False
    assert result.error_code == "SCHEDULER_PREEMPTION_UNSUPPORTED"
    assert service.calls == []


def test_checkpointable_preemption_requires_real_checkpoint_support_before_cancel():
    class CancelOnlyKernelService:
        def __init__(self) -> None:
            self.cancelled = []

        def cancel_request(self, syscall_id):
            self.cancelled.append(syscall_id)
            return KernelResponse.ok({"cancelled": [syscall_id]})

    service = CancelOnlyKernelService()
    manager = PreemptionManager(kernel_service=service)

    result = manager.request_preemption(_inspection_node(), reason="operator_suspend")

    assert result.success is False
    assert result.error_code == "SCHEDULER_PREEMPTION_UNSUPPORTED"
    assert service.cancelled == []


def test_checkpointable_preemption_preserves_checkpoint_progress_and_coverage():
    class CheckpointKernelService:
        def __init__(self) -> None:
            self.calls = []

        def checkpoint_request(self, syscall_id, **metadata):
            self.calls.append((syscall_id, metadata))
            return KernelResponse.ok(
                {
                    "checkpoint_id": "inspection_cp_7",
                    "partial_result": {"visited_waypoints": ["north_hall"]},
                    "completed_coverage": ["zone_north"],
                },
                metadata={"source_audit_id": "audit_checkpoint"},
                data={
                    "checkpoint_id": "inspection_cp_7",
                    "partial_result": {"visited_waypoints": ["north_hall"]},
                    "completed_coverage": ["zone_north"],
                },
            )

    sink = InMemoryKernelEventSink()
    service = CheckpointKernelService()
    node = _inspection_node()
    manager = PreemptionManager(kernel_service=service, audit=SchedulerAudit(event_sink=sink))

    result = manager.request_preemption(node, reason="operator_suspend")

    assert result.success is True
    assert service.calls == [
        (
            "ksc_inspection",
            {
                "reason": "operator_suspend",
                "node_id": "inspect",
                "task_graph_id": "g",
                "agent_id": "agent",
            },
        )
    ]
    assert result.metadata["checkpoint"]["checkpoint_id"] == "inspection_cp_7"
    assert result.metadata["checkpoint"]["partial_result"] == {"visited_waypoints": ["north_hall"]}
    assert result.metadata["checkpoint"]["completed_coverage"] == ["zone_north"]
    assert node.metadata["checkpoint"] == result.metadata["checkpoint"]
    assert node.metadata["checkpoints"] == [result.metadata["checkpoint"]]
    assert node.result["checkpoint"] == result.metadata["checkpoint"]
    assert any(
        event["event_type"] == "scheduler.preemption.accepted"
        and event["metadata"]["checkpoint_saved"] is True
        and event["metadata"]["completed_coverage"] == ["zone_north"]
        for event in sink.recent(limit=20)
    )


def test_checkpointable_preemption_timeout_is_audited_with_stable_error_code():
    class TimeoutKernelService:
        def checkpoint_request(self, syscall_id, **metadata):
            raise TimeoutError("checkpoint deadline exceeded")

    sink = InMemoryKernelEventSink()
    manager = PreemptionManager(kernel_service=TimeoutKernelService(), audit=SchedulerAudit(event_sink=sink))

    result = manager.request_preemption(_inspection_node(), reason="operator_suspend")

    assert result.success is False
    assert result.error_code == "SCHEDULER_PREEMPTION_TIMEOUT"
    assert any(
        event["event_type"] == "scheduler.preemption.timeout"
        and event["metadata"]["error_code"] == "SCHEDULER_PREEMPTION_TIMEOUT"
        and event["metadata"]["app_id"] == "app"
        and event["metadata"]["session_id"] == "sess"
        and event["metadata"]["task_graph_id"] == "g"
        and event["metadata"]["syscall_id"] == "ksc_inspection"
        for event in sink.recent(limit=20)
    )
    assert any(
        event["event_type"] == "scheduler.preemption.rejected"
        and event["metadata"]["error_code"] == "SCHEDULER_PREEMPTION_TIMEOUT"
        and event["metadata"]["app_id"] == "app"
        and event["metadata"]["session_id"] == "sess"
        and event["metadata"]["task_graph_id"] == "g"
        and event["metadata"]["syscall_id"] == "ksc_inspection"
        for event in sink.recent(limit=20)
    )
