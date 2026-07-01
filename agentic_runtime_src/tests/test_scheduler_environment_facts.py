from __future__ import annotations

import pytest

from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, QueryType, TaskGraph, TaskNode
from agentic_os.kernel.scheduler.environment import EnvironmentFact, EnvironmentStore
from agentic_os.kernel.scheduler.errors import SchedulerError
from agentic_os.kernel.scheduler.models import now_ns
from agentic_os.kernel.scheduler.preconditions import Precondition, PreconditionEvaluator
from agentic_os.kernel.system_call import KernelResponse
from agentic_os.kernel.system_call.executor import SyscallExecutionResult
from agentic_os.kernel.system_call.models import KernelSyscall


def test_environment_fact_reuse_requires_traceable_source_and_precondition():
    store = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0, "workspace_zone": "table"},
        source_node_id="inspect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=10_000_000_000,
        confidence=0.92,
        world_epoch=store.world_epoch,
        schema_id="",
        real_dependency="ros_bridge",
    )
    store.put(fact)

    accepted, flags = store.validate_reuse("cup_pose", min_confidence=0.8)
    result = PreconditionEvaluator(store).evaluate(
        [Precondition("cup_pose", operator="within_workspace_zone", expected="table", min_confidence=0.8)],
        fact.timestamp_ns,
    )

    assert accepted is True
    assert flags["source_real_ok"] is True
    assert result.success is True


def test_environment_fact_rejects_unverified_source():
    store = EnvironmentStore()
    fact = EnvironmentFact.from_dict(
        {
            "key": "cup_pose",
            "value": {"x": 1},
            "source_node_id": "",
            "source_capability": "perception.detect_cup",
            "source_syscall_id": "ksc",
            "source_audit_id": "audit",
            "source_result_hash": "hash",
            "timestamp_ns": now_ns(),
            "ttl_ns": 10,
            "confidence": 0.9,
            "world_epoch": 0,
            "schema_id": "",
            "real_dependency": "ros_bridge",
        }
    )

    with pytest.raises(SchedulerError, match="SCHEDULER_FACT_SOURCE_UNVERIFIED"):
        store.put(fact)


def test_environment_fact_rejects_llm_dependency_as_real_source():
    store = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="planner_summary",
        value={"summary": "done"},
        source_node_id="planner",
        source_capability="llm.plan",
        source_syscall_id="ksc_real_llm",
        source_audit_id="audit_real_llm",
        source_result={"summary": "done"},
        ttl_ns=10_000_000_000,
        confidence=0.9,
        world_epoch=store.world_epoch,
        schema_id="",
        real_dependency="llm_provider",
    )

    with pytest.raises(SchedulerError, match="SCHEDULER_FACT_SOURCE_UNVERIFIED"):
        store.put(fact)


def test_environment_fact_rejects_mock_dependency_as_real_source():
    store = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="detect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_mock",
        source_audit_id="audit_mock",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=10_000_000_000,
        confidence=0.9,
        world_epoch=store.world_epoch,
        schema_id="",
        real_dependency="mock_backend",
    )

    with pytest.raises(SchedulerError, match="SCHEDULER_FACT_SOURCE_UNVERIFIED"):
        store.put(fact)


def test_precondition_rejects_unverified_fact_loaded_into_store():
    store = EnvironmentStore()
    fact = EnvironmentFact.from_dict(
        {
            "fact_id": "fact_corrupt",
            "key": "cup_pose",
            "value": {"x": 1},
            "source_node_id": "inspect",
            "source_capability": "perception.detect_cup",
            "source_syscall_id": "ksc_real",
            "source_audit_id": "",
            "source_result_hash": "hash",
            "timestamp_ns": now_ns(),
            "ttl_ns": 10_000_000_000,
            "confidence": 0.9,
            "world_epoch": store.world_epoch,
            "schema_id": "",
            "real_dependency": "ros_bridge",
        }
    )
    store._facts_by_key[fact.key] = fact

    result = PreconditionEvaluator(store).evaluate(
        [Precondition("cup_pose", min_confidence=0.8)],
        fact.timestamp_ns,
    )

    assert result.success is False
    assert result.error_code == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert result.metadata["fact_key"] == "cup_pose"
    assert result.metadata["fact_id"] == "fact_corrupt"


def test_precondition_returns_stale_for_expired_traceable_fact():
    store = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1},
        source_node_id="inspect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1}},
        ttl_ns=1,
        confidence=0.9,
        world_epoch=store.world_epoch,
        schema_id="",
        real_dependency="ros_bridge",
    )
    store.put(fact)

    result = PreconditionEvaluator(store).evaluate(
        [Precondition("cup_pose", min_confidence=0.8)],
        fact.timestamp_ns + 2,
    )

    assert result.success is False
    assert result.error_code == "SCHEDULER_FACT_STALE"
    assert result.metadata["fact_key"] == "cup_pose"
    assert result.metadata["fact_id"] == fact.fact_id


def test_environment_fact_value_schema_is_validated():
    store = EnvironmentStore()
    store.register_schema("pose.schema.json", {"type": "object", "required": ["x"], "properties": {"x": {"type": "number"}}})
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": "not-a-number"},
        source_node_id="inspect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": "not-a-number"}},
        ttl_ns=10_000_000_000,
        confidence=0.92,
        world_epoch=store.world_epoch,
        schema_id="pose.schema.json",
        real_dependency="ros_bridge",
    )

    with pytest.raises(SchedulerError, match="SCHEDULER_FACT_SCHEMA_INVALID"):
        store.put(fact)


def test_environment_fact_rejects_unknown_declared_schema_id():
    store = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": 1.0},
        source_node_id="inspect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": 1.0}},
        ttl_ns=10_000_000_000,
        confidence=0.92,
        world_epoch=store.world_epoch,
        schema_id="missing_pose.schema.json",
        real_dependency="ros_bridge",
    )

    with pytest.raises(SchedulerError) as error:
        store.put(fact)

    assert error.value.error_code == "SCHEDULER_FACT_SCHEMA_INVALID"
    assert error.value.metadata["schema_id"] == "missing_pose.schema.json"


def test_environment_fact_reuse_revalidates_value_schema():
    store = EnvironmentStore()
    fact = EnvironmentFact.from_dict(
        {
            "fact_id": "fact_bad_pose",
            "key": "cup_pose",
            "value": {"x": "not-a-number"},
            "source_node_id": "inspect",
            "source_capability": "perception.detect_cup",
            "source_syscall_id": "ksc_real",
            "source_audit_id": "audit_real",
            "source_result_hash": "hash",
            "timestamp_ns": now_ns(),
            "ttl_ns": 10_000_000_000,
            "confidence": 0.92,
            "world_epoch": store.world_epoch,
            "schema_id": "cup_pose.schema.json",
            "real_dependency": "ros_bridge",
        }
    )
    store._facts_by_key[fact.key] = fact

    accepted, flags = store.validate_reuse("cup_pose", min_confidence=0.8, schema_id="cup_pose.schema.json")

    assert accepted is False
    assert flags["schema_ok"] is False
    assert flags["reject_reason"] == "SCHEDULER_REUSE_SCHEMA_OK_FAILED"


def test_precondition_matches_schema_returns_structured_schema_error():
    store = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_pose",
        value={"x": "not-a-number"},
        source_node_id="inspect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_pose": {"x": "not-a-number"}},
        ttl_ns=10_000_000_000,
        confidence=0.92,
        world_epoch=store.world_epoch,
        schema_id="",
        real_dependency="ros_bridge",
    )
    store.put(fact)

    result = PreconditionEvaluator(store).evaluate(
        [
            Precondition(
                "cup_pose",
                operator="matches_schema",
                expected={"type": "object", "required": ["x"], "properties": {"x": {"type": "number"}}},
            )
        ],
        fact.timestamp_ns,
    )

    assert result.success is False
    assert result.error_code == "SCHEDULER_FACT_SCHEMA_INVALID"


def test_precondition_type_mismatch_returns_structured_not_met():
    store = EnvironmentStore()
    fact = EnvironmentFact.create(
        key="cup_count",
        value={"count": 1},
        source_node_id="inspect",
        source_capability="perception.detect_cup",
        source_syscall_id="ksc_real",
        source_audit_id="audit_real",
        source_result={"cup_count": {"count": 1}},
        ttl_ns=10_000_000_000,
        confidence=0.92,
        world_epoch=store.world_epoch,
        schema_id="",
        real_dependency="ros_bridge",
    )
    store.put(fact)

    result = PreconditionEvaluator(store).evaluate([Precondition("cup_count", operator="gt", expected=0)], fact.timestamp_ns)

    assert result.success is False
    assert result.error_code == "SCHEDULER_PRECONDITION_NOT_MET"


class ResultKernelService:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    def execute_request(self, agent_name, query, timeout_s=None):
        self.calls.append((agent_name, query, timeout_s))
        syscall = KernelSyscall.create(agent_name, "robot_sensor", query.operation_type, query.params)
        syscall.syscall_id = "ksc_real_fact"
        syscall.target = "robot_sensor"
        return SyscallExecutionResult(
            syscall=syscall,
            response=KernelResponse.ok(self.payload, metadata={"audit_id": "audit_real"}, data=self.payload),
            success=True,
            metadata={"queue_name": "robot_sensor", "audit_id": "audit_real"},
        )


def _fact_producer_graph() -> TaskGraph:
    node = TaskNode.create(
        node_id="detect",
        task_graph_id="g_fact",
        user_goal_id="goal_fact",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="perception.detect_cup",
        operation_type="perception.detect_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        metadata={
            "produces_fact_specs": [
                {
                    "fact_key": "cup_pose",
                    "value_key": "cup_pose",
                    "ttl_ns": 30_000_000_000,
                    "confidence_key": "confidence",
                }
            ]
        },
    )
    return TaskGraph.create(
        task_graph_id="g_fact",
        user_goal_id="goal_fact",
        root_goal="detect cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"detect": node},
    )


def test_scheduler_ingests_declared_fact_from_traceable_result():
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        kernel_service=ResultKernelService({"cup_pose": {"x": 1.0}, "confidence": 0.91, "backend": "ros_bridge", "audit_id": "audit_real"}),
    )
    scheduler.submit_graph(_fact_producer_graph())

    decision = scheduler.tick(max_dispatch=1)[0]
    fact = scheduler.environment_store.get("cup_pose")

    assert decision["success"] is True
    assert fact is not None
    assert fact.source_syscall_id == "ksc_real_fact"
    assert fact.source_audit_id == "audit_real"


def test_scheduler_fact_creation_ingests_dynamic_graph_event_and_unblocks_consumer():
    sink = InMemoryKernelEventSink()
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(event_sink=sink),
        {},
        kernel_service=ResultKernelService({"cup_pose": {"x": 1.0}, "confidence": 0.91, "backend": "ros_bridge", "audit_id": "audit_real"}),
        event_sink=sink,
    )
    consumer = TaskNode.create(
        node_id="pick",
        task_graph_id="g_consume_fact",
        user_goal_id="goal_consume_fact",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.pick_cup",
        operation_type="robot.pick_cup",
        query_type=QueryType.ROBOT_CAPABILITY,
        consumes_facts=["cup_pose"],
        preconditions=[Precondition("cup_pose", min_confidence=0.8)],
    )
    consumer_graph = TaskGraph.create(
        task_graph_id="g_consume_fact",
        user_goal_id="goal_consume_fact",
        root_goal="pick cup",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"pick": consumer},
    )
    scheduler.submit_graph(consumer_graph)
    assert scheduler.graph_store.get_node("pick").status == "blocked"
    scheduler.submit_graph(_fact_producer_graph())

    decision = scheduler.tick(max_dispatch=1)[0]
    consumer_after_fact = scheduler.graph_store.get_node("pick")
    events = sink.recent(limit=120)

    assert decision["success"] is True
    assert consumer_after_fact.status == "ready"
    assert any(
        event["event_type"] == "scheduler.reconstruction.staged"
        and event["metadata"]["dynamic_event_type"] == "environment_fact_created"
        and event["metadata"]["fact_key"] == "cup_pose"
        for event in events
    )
    assert any(
        event["event_type"] == "scheduler.reconstruction.committed"
        and event["metadata"]["dynamic_event_type"] == "environment_fact_created"
        and "pick" in event["metadata"]["dirty_nodes_refreshed"]
        for event in events
    )


def test_scheduler_fact_expiry_ingests_dynamic_graph_event_and_blocks_ready_consumer_before_dispatch():
    sink = InMemoryKernelEventSink()
    service = ResultKernelService({"ok": True, "audit_id": "audit_real"})
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, kernel_service=service, event_sink=sink)
    fact = EnvironmentFact.create(
        key="door_open",
        value=True,
        source_node_id="inspect",
        source_capability="perception.check_door",
        source_syscall_id="ksc_real_door",
        source_audit_id="audit_real_door",
        source_result={"door_open": True},
        ttl_ns=30_000_000_000,
        confidence=0.99,
        world_epoch=scheduler.environment_store.world_epoch,
        schema_id="",
        real_dependency="ros_bridge",
    )
    scheduler.environment_store.put(fact)
    node = TaskNode.create(
        node_id="report_expiring_fact",
        task_graph_id="g_expiring_fact",
        user_goal_id="goal_expiring_fact",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "door is open"},
        preconditions=[Precondition("door_open", operator="eq", expected=True)],
    )
    graph = TaskGraph.create(
        task_graph_id="g_expiring_fact",
        user_goal_id="goal_expiring_fact",
        root_goal="report door",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"report_expiring_fact": node},
    )
    scheduler.submit_graph(graph)
    assert scheduler.graph_store.get_node("report_expiring_fact").status == "ready"
    fact.timestamp_ns = 1
    fact.ttl_ns = 1

    decisions = scheduler.tick(max_dispatch=0)
    blocked = scheduler.graph_store.get_node("report_expiring_fact")
    events = sink.recent(limit=120)

    assert decisions == []
    assert service.calls == []
    assert blocked.status == "blocked"
    assert blocked.error_code == "SCHEDULER_FACT_STALE"
    assert any(
        event["event_type"] == "scheduler.environment.fact_expired"
        and event["metadata"]["fact_key"] == "door_open"
        for event in events
    )
    assert any(
        event["event_type"] == "scheduler.reconstruction.committed"
        and event["metadata"]["dynamic_event_type"] == "environment_fact_expired"
        and event["metadata"]["dirty_nodes_refreshed"] == ["report_expiring_fact"]
        for event in events
    )


def test_scheduler_fails_node_when_declared_fact_is_missing_from_result():
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        kernel_service=ResultKernelService({"confidence": 0.91, "backend": "ros_bridge", "audit_id": "audit_real"}),
    )
    scheduler.submit_graph(_fact_producer_graph())

    decision = scheduler.tick(max_dispatch=1)[0]
    node = scheduler.graph_store.get_node("detect")

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_FACT_EXTRACTION_FAILED"
    assert node.status == "failed"
    assert node.error_code == "SCHEDULER_FACT_EXTRACTION_FAILED"
    assert scheduler.environment_store.get("cup_pose") is None


def test_scheduler_fails_fact_creation_when_confidence_evidence_is_missing():
    graph = _fact_producer_graph()
    graph.nodes["detect"].metadata["produces_fact_specs"][0].pop("confidence_key")
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        kernel_service=ResultKernelService({"cup_pose": {"x": 1.0}, "backend": "ros_bridge", "audit_id": "audit_real"}),
    )
    scheduler.submit_graph(graph)

    decision = scheduler.tick(max_dispatch=1)[0]
    node = scheduler.graph_store.get_node("detect")

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_FACT_EXTRACTION_FAILED"
    assert node.status == "failed"
    assert node.error_code == "SCHEDULER_FACT_EXTRACTION_FAILED"
    assert scheduler.environment_store.get("cup_pose") is None


def test_scheduler_allows_fact_confidence_from_explicit_capability_contract():
    graph = _fact_producer_graph()
    fact_spec = graph.nodes["detect"].metadata["produces_fact_specs"][0]
    fact_spec.pop("confidence_key")
    fact_spec["confidence"] = 0.84
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        kernel_service=ResultKernelService({"cup_pose": {"x": 1.0}, "backend": "ros_bridge", "audit_id": "audit_real"}),
    )
    scheduler.submit_graph(graph)

    decision = scheduler.tick(max_dispatch=1)[0]
    fact = scheduler.environment_store.get("cup_pose")

    assert decision["success"] is True
    assert fact is not None
    assert fact.confidence == 0.84
    assert fact.real_dependency == "ros_bridge"


def test_scheduler_fails_fact_creation_when_real_dependency_evidence_is_missing():
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        kernel_service=ResultKernelService({"cup_pose": {"x": 1.0}, "confidence": 0.91, "audit_id": "audit_real"}),
    )
    scheduler.submit_graph(_fact_producer_graph())

    decision = scheduler.tick(max_dispatch=1)[0]
    node = scheduler.graph_store.get_node("detect")

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert node.status == "failed"
    assert node.error_code == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert scheduler.environment_store.get("cup_pose") is None


def test_scheduler_fails_fact_creation_when_dependency_evidence_is_llm():
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        kernel_service=ResultKernelService({"cup_pose": {"x": 1.0}, "confidence": 0.91, "backend": "llm_provider", "audit_id": "audit_real"}),
    )
    scheduler.submit_graph(_fact_producer_graph())

    decision = scheduler.tick(max_dispatch=1)[0]
    node = scheduler.graph_store.get_node("detect")

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert node.status == "failed"
    assert node.error_code == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert scheduler.environment_store.get("cup_pose") is None


def test_scheduler_fails_fact_creation_when_dependency_evidence_is_mock():
    scheduler = EnvironmentAwareDAGScheduler(
        KernelQueueStore(),
        {},
        kernel_service=ResultKernelService({"cup_pose": {"x": 1.0}, "confidence": 0.91, "backend": "mock_backend", "audit_id": "audit_real"}),
    )
    scheduler.submit_graph(_fact_producer_graph())

    decision = scheduler.tick(max_dispatch=1)[0]
    node = scheduler.graph_store.get_node("detect")

    assert decision["success"] is False
    assert decision["error_code"] == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert node.status == "failed"
    assert node.error_code == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert scheduler.environment_store.get("cup_pose") is None


def test_scheduler_rechecks_ready_node_preconditions_before_dispatch():
    sink = InMemoryKernelEventSink()
    service = ResultKernelService({"ok": True, "audit_id": "audit_real"})
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, kernel_service=service, event_sink=sink)
    fact = EnvironmentFact.create(
        key="door_open",
        value=True,
        source_node_id="inspect",
        source_capability="perception.check_door",
        source_syscall_id="ksc_real_door",
        source_audit_id="audit_real_door",
        source_result={"door_open": True},
        ttl_ns=30_000_000_000,
        confidence=0.99,
        world_epoch=scheduler.environment_store.world_epoch,
        schema_id="",
        real_dependency="ros_bridge",
    )
    scheduler.environment_store.put(fact)
    node = TaskNode.create(
        node_id="report",
        task_graph_id="g_precondition",
        user_goal_id="goal_precondition",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "door is open"},
        preconditions=[Precondition("door_open", operator="eq", expected=True)],
    )
    graph = TaskGraph.create(
        task_graph_id="g_precondition",
        user_goal_id="goal_precondition",
        root_goal="report door",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"report": node},
    )

    response = scheduler.submit_graph(graph)
    assert response.success is True
    assert scheduler.graph_store.get_node("report").status == "ready"

    scheduler.environment_store.world_epoch += 1
    decisions = scheduler.tick(max_dispatch=1)

    blocked = scheduler.graph_store.get_node("report")
    assert decisions == []
    assert service.calls == []
    assert blocked.status == "blocked"
    assert blocked.error_code == "SCHEDULER_FACT_WORLD_EPOCH_STALE"
    assert any(
        event.get("event_type") == "scheduler.node.blocked" and event.get("metadata", {}).get("node_id") == "report"
        for event in sink.recent(limit=20)
    )


def test_scheduler_blocks_dispatch_when_fact_source_becomes_unverified():
    sink = InMemoryKernelEventSink()
    service = ResultKernelService({"ok": True, "audit_id": "audit_real"})
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(event_sink=sink), {}, kernel_service=service, event_sink=sink)
    fact = EnvironmentFact.from_dict(
        {
            "fact_id": "fact_loaded_unverified",
            "key": "door_open",
            "value": True,
            "source_node_id": "inspect",
            "source_capability": "perception.check_door",
            "source_syscall_id": "ksc_real_door",
            "source_audit_id": "",
            "source_result_hash": "hash",
            "timestamp_ns": now_ns(),
            "ttl_ns": 30_000_000_000,
            "confidence": 0.99,
            "world_epoch": scheduler.environment_store.world_epoch,
            "schema_id": "",
            "real_dependency": "ros_bridge",
        }
    )
    scheduler.environment_store._facts_by_key[fact.key] = fact
    node = TaskNode.create(
        node_id="report_unverified_fact",
        task_graph_id="g_unverified_fact",
        user_goal_id="goal_unverified_fact",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        operation_type="skill_call",
        query_type=QueryType.SKILL,
        params={"message": "door is open"},
        preconditions=[Precondition("door_open", operator="eq", expected=True)],
    )
    graph = TaskGraph.create(
        task_graph_id="g_unverified_fact",
        user_goal_id="goal_unverified_fact",
        root_goal="report door",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"report_unverified_fact": node},
    )

    response = scheduler.submit_graph(graph)

    blocked = scheduler.graph_store.get_node("report_unverified_fact")
    assert response.success is True
    assert service.calls == []
    assert blocked.status == "blocked"
    assert blocked.error_code == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert any(
        event.get("event_type") == "scheduler.node.blocked"
        and event.get("metadata", {}).get("node_id") == "report_unverified_fact"
        and event.get("metadata", {}).get("fact_id") == "fact_loaded_unverified"
        for event in sink.recent(limit=40)
    )
