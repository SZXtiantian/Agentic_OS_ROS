from __future__ import annotations

import json
from types import SimpleNamespace

from jsonschema import Draft202012Validator

from agentic_os.kernel.capability import CapabilityRegistry
from agentic_os.kernel.hooks import KernelQueueStore
from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, QueryType, ResourceRequest, TaskGraph, TaskGraphStatus, TaskNodeStatus, TaskGraphStore, TaskNode, TypedEdge
from agentic_os.kernel.scheduler.admission import AdmissionController


REQUIRED_SCHEDULER_SCHEMA_FILES = {
    "task_graph.schema.json",
    "task_node.schema.json",
    "fusion_plan.schema.json",
    "environment_fact.schema.json",
    "debug_snapshot.schema.json",
}


def test_required_scheduler_json_schemas_are_present_and_metaschema_valid(runtime_src):
    schema_root = runtime_src / "agentic_os" / "kernel" / "scheduler" / "schemas"

    for schema_name in sorted(REQUIRED_SCHEDULER_SCHEMA_FILES):
        schema_path = schema_root / schema_name
        assert schema_path.exists(), schema_name
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema.get("$id") == schema_name


def test_task_graph_models_are_json_serializable_and_store_indexes():
    first = TaskNode.create(
        node_id="n1",
        task_graph_id="g1",
        user_goal_id="goal1",
        agent_id="agent1",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.inspect_area",
        query_type=QueryType.ROBOT_CAPABILITY,
        workspace_zone="zone_a",
        produces_facts=["cup_pose"],
    )
    second = TaskNode.create(
        node_id="n2",
        task_graph_id="g1",
        user_goal_id="goal1",
        agent_id="agent1",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        consumes_facts=["cup_pose"],
    )
    graph = TaskGraph.create(
        task_graph_id="g1",
        user_goal_id="goal1",
        root_goal="inspect",
        agent_id="agent1",
        app_id="app",
        session_id="sess",
        nodes={"n1": first, "n2": second},
        edges=[TypedEdge("e1", "n1", "n2")],
    )
    payload = graph.to_dict()
    restored = TaskGraph.from_dict(payload)
    store = TaskGraphStore()
    store.add_graph(restored)

    assert restored.nodes["n2"].dependencies == {"n1"}
    assert store.global_dag.node_index_by_agent["agent1"] == {"n1", "n2"}
    assert store.global_dag.node_index_by_fact["cup_pose"] == {"n1", "n2"}


def test_direct_task_graph_edges_drive_ready_extraction():
    first = TaskNode.create(
        node_id="first",
        task_graph_id="g_ready_edges",
        user_goal_id="goal_ready_edges",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    second = TaskNode.create(
        node_id="second",
        task_graph_id="g_ready_edges",
        user_goal_id="goal_ready_edges",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id="g_ready_edges",
        user_goal_id="goal_ready_edges",
        root_goal="ordered report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"first": first, "second": second},
        edges=[TypedEdge("edge_first_second", "first", "second")],
    )
    scheduler = EnvironmentAwareDAGScheduler(KernelQueueStore(), {})

    response = scheduler.submit_graph(graph)

    assert response.success is True
    assert scheduler.graph_store.get_node("second").dependencies == {"first"}
    assert scheduler.graph_store.get_node("second").status == TaskNodeStatus.WAITING
    assert [item["node_id"] for item in scheduler.ready_queue.snapshot()] == ["first"]


def test_task_graph_store_derives_graph_status_from_node_lifecycle():
    first = TaskNode.create(
        node_id="n1",
        task_graph_id="g_status",
        user_goal_id="goal_status",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    second = TaskNode.create(
        node_id="n2",
        task_graph_id="g_status",
        user_goal_id="goal_status",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id="g_status",
        user_goal_id="goal_status",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n1": first, "n2": second},
    )
    store = TaskGraphStore()
    store.add_graph(graph)

    store.mark_status("n1", TaskNodeStatus.RUNNING)
    assert store.get_graph("g_status").status == TaskGraphStatus.RUNNING

    store.mark_status("n1", TaskNodeStatus.COMPLETED)
    assert store.get_graph("g_status").status == TaskGraphStatus.RUNNING

    store.mark_status("n2", TaskNodeStatus.COMPLETED)
    assert store.get_graph("g_status").status == TaskGraphStatus.COMPLETED

    stale = TaskNode.create(
        node_id="stale",
        task_graph_id="g_stale",
        user_goal_id="goal_stale",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    stale_graph = TaskGraph.create(
        task_graph_id="g_stale",
        user_goal_id="goal_stale",
        root_goal="stale",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"stale": stale},
    )
    store.add_graph(stale_graph)
    store.mark_status("stale", TaskNodeStatus.STALE, error_code="SCHEDULER_RESOURCE_LEASE_EXPIRED")

    assert store.get_graph("g_stale").status == TaskGraphStatus.FAILED


def test_admission_validates_each_task_node_schema():
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type="unsupported",
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node},
    )

    result = AdmissionController().admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_NODE_SCHEMA_INVALID"


def test_admission_rejects_llm_node_that_claims_physical_fact_output():
    node = TaskNode.create(
        node_id="llm_pose",
        task_graph_id="g_llm_pose",
        user_goal_id="goal_llm_pose",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="llm.plan",
        operation_type="chat",
        query_type=QueryType.LLM,
        produces_facts=["cup_pose"],
    )
    graph = TaskGraph.create(
        task_graph_id="g_llm_pose",
        user_goal_id="goal_llm_pose",
        root_goal="plan",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"llm_pose": node},
    )

    result = AdmissionController().admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_FACT_SOURCE_UNVERIFIED"
    assert result.metadata["fact_keys"] == ["cup_pose"]


def test_admission_rejects_llm_environment_fact_extraction_specs():
    node = TaskNode.create(
        node_id="llm_fact_spec",
        task_graph_id="g_llm_fact_spec",
        user_goal_id="goal_llm_fact_spec",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="llm.plan",
        operation_type="chat",
        query_type=QueryType.LLM,
        metadata={"produces_fact_specs": [{"fact_key": "planner_summary"}]},
    )
    graph = TaskGraph.create(
        task_graph_id="g_llm_fact_spec",
        user_goal_id="goal_llm_fact_spec",
        root_goal="plan",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"llm_fact_spec": node},
    )

    result = AdmissionController().admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_FACT_SOURCE_UNVERIFIED"


def test_admission_validates_resource_request_schema_with_priority_ceiling():
    node = TaskNode.create(
        node_id="resource_node",
        task_graph_id="g_resource_schema",
        user_goal_id="goal_resource_schema",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        resources=[
            ResourceRequest(
                resource_id="base",
                mode="exclusive",
                amount=1,
                lease_ttl_ns=100_000_000,
                priority_ceiling=50,
                reason="navigation",
            )
        ],
    )
    graph = TaskGraph.create(
        task_graph_id="g_resource_schema",
        user_goal_id="goal_resource_schema",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"resource_node": node},
    )

    result = AdmissionController().validate_node_schema(node.to_dict())

    assert result.success is True


def test_admission_rejects_invalid_resource_request_schema_before_runtime_arbitration():
    node = TaskNode.create(
        node_id="bad_resource_node",
        task_graph_id="g_bad_resource_schema",
        user_goal_id="goal_bad_resource_schema",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
    )
    payload = node.to_dict()
    payload["resources"] = [
        {
            "resource_id": "base",
            "mode": "borrowed",
            "amount": 0,
            "lease_ttl_ns": 0,
            "priority_ceiling": -1,
        }
    ]

    result = AdmissionController().validate_node_schema(payload)

    assert result.success is False
    assert result.error_code == "SCHEDULER_NODE_SCHEMA_INVALID"
    assert result.metadata["node_id"] == "bad_resource_node"


def test_admission_validates_raw_graph_resource_schema_before_model_coercion():
    node = TaskNode.create(
        node_id="resource_node",
        task_graph_id="g_raw_resource_schema",
        user_goal_id="goal_raw_resource_schema",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        resources=[
            ResourceRequest(
                resource_id="base",
                mode="exclusive",
                amount=2,
                lease_ttl_ns=100_000_000,
                priority_ceiling=10,
            )
        ],
    )
    graph = TaskGraph.create(
        task_graph_id="g_raw_resource_schema",
        user_goal_id="goal_raw_resource_schema",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"resource_node": node},
    )
    payload = graph.to_dict()
    payload["nodes"]["resource_node"]["resources"][0]["amount"] = "2"

    result = AdmissionController().validate_graph_payload_schema(payload)

    assert result.success is False
    assert result.error_code == "SCHEDULER_NODE_SCHEMA_INVALID"
    assert result.metadata["node_id"] == "resource_node"
    assert result.metadata["node_key"] == "resource_node"


def test_admission_rejects_non_json_serializable_task_node_payload():
    node = TaskNode.create(
        node_id="callback_node",
        task_graph_id="g_callback",
        user_goal_id="goal_callback",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        params={"callback": lambda: None},
    )
    graph = TaskGraph.create(
        task_graph_id="g_callback",
        user_goal_id="goal_callback",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"callback_node": node},
    )

    result = AdmissionController().admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_NODE_SCHEMA_INVALID"
    assert result.metadata["json_path"] == "$.params.callback"
    assert result.metadata["json_value_type"] == "function"


def test_admission_rejects_non_json_serializable_task_graph_payload():
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g_non_finite",
        user_goal_id="goal_non_finite",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id="g_non_finite",
        user_goal_id="goal_non_finite",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node},
        edges=[TypedEdge("edge_nan", "n", "n", metadata={"score": float("nan")})],
    )

    result = AdmissionController().admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_GRAPH_SCHEMA_INVALID"
    assert result.metadata["json_path"] == "$.edges[0].metadata.score"
    assert result.metadata["json_value_type"] == "non_finite_float"


def test_admission_rejects_graph_node_identity_mismatch():
    node = TaskNode.create(
        node_id="n",
        task_graph_id="g",
        user_goal_id="goal",
        agent_id="other_agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
    )
    graph = TaskGraph.create(
        task_graph_id="g",
        user_goal_id="goal",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"n": node},
    )

    result = AdmissionController().admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_GRAPH_SCHEMA_INVALID"
    assert result.metadata["mismatches"]["agent_id"]["node"] == "other_agent"


def test_admission_rejects_direct_nav2_moveit_or_ros_interfaces():
    cases = [
        ("nav2_direct", "nav2.navigate_to_pose", "nav2.navigate_to_pose", "capability"),
        ("navigate_to_pose_direct", "robot.navigate_to", "/navigate_to_pose", "operation_type"),
        ("moveit_direct", "moveit.plan", "moveit.plan", "capability"),
        ("ros2_direct", "ros2.service.call", "ros2.service.call", "capability"),
    ]
    for node_id, capability, operation_type, field in cases:
        node = TaskNode.create(
            node_id=node_id,
            task_graph_id=f"g_{node_id}",
            user_goal_id=f"goal_{node_id}",
            agent_id="agent",
            agent_name="app",
            app_id="app",
            session_id="sess",
            capability=capability,
            operation_type=operation_type,
            query_type=QueryType.ROBOT_CAPABILITY,
            params={"place": "kitchen"},
        )
        graph = TaskGraph.create(
            task_graph_id=f"g_{node_id}",
            user_goal_id=f"goal_{node_id}",
            root_goal="navigate",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            nodes={node_id: node},
        )

        result = AdmissionController().admit(graph)

        assert result.success is False
        assert result.error_code == "SCHEDULER_ADMISSION_REJECTED"
        assert result.metadata["node_id"] == node_id
        assert result.metadata["field"] == field


def test_admission_rejects_low_level_robot_markers_in_payload():
    node = TaskNode.create(
        node_id="low_level_payload",
        task_graph_id="g_low_level_payload",
        user_goal_id="goal_low_level_payload",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        operation_type="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"ros2_backend_action_type": "nav2_msgs/action/NavigateToPose"},
    )
    graph = TaskGraph.create(
        task_graph_id="g_low_level_payload",
        user_goal_id="goal_low_level_payload",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"low_level_payload": node},
    )

    result = AdmissionController().admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_ADMISSION_REJECTED"
    assert result.metadata["marker"] == "nav2_msgs/action"


def test_admission_rejects_registered_robot_capability_missing_runtime_contract_fields():
    class LooseRegistry:
        def __init__(self, spec):
            self.spec = spec

        def get(self, name):
            return self.spec if name == self.spec.name else None

    cases = [
        (
            SimpleNamespace(
                name="robot.navigate_to",
                input_schema={},
                output_schema={},
                permissions=[],
                safety_constraints={"require_estop_released": True},
                resource_locks=["base"],
                observability={"audit": True},
            ),
            "permissions",
        ),
        (
            SimpleNamespace(
                name="robot.navigate_to",
                input_schema={},
                output_schema={},
                permissions=["robot.move"],
                safety_constraints={},
                resource_locks=["base"],
                observability={"audit": True},
            ),
            "safety_constraints",
        ),
        (
            SimpleNamespace(
                name="robot.navigate_to",
                input_schema={},
                output_schema={},
                permissions=["robot.move"],
                safety_constraints={"require_estop_released": True},
                resource_locks=[],
                observability={"audit": True},
            ),
            "resource_locks",
        ),
        (
            SimpleNamespace(
                name="robot.navigate_to",
                input_schema={},
                output_schema={},
                permissions=["robot.move"],
                safety_constraints={"require_estop_released": True},
                resource_locks=["base"],
                observability={"audit": False},
            ),
            "observability.audit",
        ),
    ]

    for spec, missing_field in cases:
        node = TaskNode.create(
            node_id=f"nav_{missing_field.replace('.', '_')}",
            task_graph_id=f"g_{missing_field.replace('.', '_')}",
            user_goal_id=f"goal_{missing_field.replace('.', '_')}",
            agent_id="agent",
            agent_name="app",
            app_id="app",
            session_id="sess",
            capability="robot.navigate_to",
            operation_type="robot.navigate_to",
            query_type=QueryType.ROBOT_CAPABILITY,
            params={"place": "kitchen"},
        )
        graph = TaskGraph.create(
            task_graph_id=node.task_graph_id,
            user_goal_id=node.user_goal_id,
            root_goal="navigate",
            agent_id="agent",
            app_id="app",
            session_id="sess",
            nodes={node.node_id: node},
        )

        result = AdmissionController(capability_registry=LooseRegistry(spec)).admit(graph)

        assert result.success is False
        assert result.error_code == "SCHEDULER_CAPABILITY_CONTRACT_INVALID"
        assert result.metadata["missing_contract_field"] == missing_field


def test_admission_allows_registered_read_only_robot_capability_without_resource_lock():
    class LooseRegistry:
        def get(self, name):
            if name != "robot.get_state":
                return None
            return SimpleNamespace(
                name="robot.get_state",
                input_schema={},
                output_schema={"type": "object"},
                permissions=["robot.state.read"],
                safety_constraints={"require_estop_released": False},
                resource_locks=[],
                observability={"audit": True},
            )

    node = TaskNode.create(
        node_id="state",
        task_graph_id="g_state",
        user_goal_id="goal_state",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.get_state",
        operation_type="robot.get_state",
        query_type=QueryType.ROBOT_CAPABILITY,
    )
    graph = TaskGraph.create(
        task_graph_id="g_state",
        user_goal_id="goal_state",
        root_goal="state",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"state": node},
    )

    result = AdmissionController(capability_registry=LooseRegistry()).admit(graph)

    assert result.success is True
    assert node.required_permissions == ["robot.state.read"]
    assert node.resources == []


def test_admission_validates_registered_capability_input_schema_and_enriches_contract(runtime_src):
    registry = CapabilityRegistry().load_skill_manifests(runtime_src / "system_skills")
    invalid = TaskNode.create(
        node_id="bad_report",
        task_graph_id="g_bad",
        user_goal_id="goal_bad",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="report.say",
        query_type=QueryType.SKILL,
        params={},
    )
    invalid_graph = TaskGraph.create(
        task_graph_id="g_bad",
        user_goal_id="goal_bad",
        root_goal="report",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"bad_report": invalid},
    )

    invalid_result = AdmissionController(capability_registry=registry).admit(invalid_graph)

    assert invalid_result.success is False
    assert invalid_result.error_code == "SCHEDULER_CAPABILITY_CONTRACT_INVALID"

    navigate = TaskNode.create(
        node_id="nav",
        task_graph_id="g_nav",
        user_goal_id="goal_nav",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"place": "kitchen"},
    )
    valid_graph = TaskGraph.create(
        task_graph_id="g_nav",
        user_goal_id="goal_nav",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"nav": navigate},
    )

    valid_result = AdmissionController(capability_registry=registry).admit(valid_graph)

    assert valid_result.success is True
    assert navigate.required_permissions == ["robot.move"]
    assert navigate.safety_constraints["require_estop_released"] is True
    assert [request.resource_id for request in navigate.resources] == ["base"]
    assert navigate.input_schema_id == "capability:robot.navigate_to:input"


def test_admission_merges_registered_permissions_and_rejects_safety_downgrade(runtime_src):
    registry = CapabilityRegistry().load_skill_manifests(runtime_src / "system_skills")
    node = TaskNode.create(
        node_id="nav",
        task_graph_id="g_nav_contract",
        user_goal_id="goal_nav_contract",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"place": "kitchen"},
        required_permissions=["report.say"],
        safety_constraints={"require_estop_released": False},
    )
    graph = TaskGraph.create(
        task_graph_id="g_nav_contract",
        user_goal_id="goal_nav_contract",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"nav": node},
    )

    result = AdmissionController(capability_registry=registry).admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_CAPABILITY_CONTRACT_INVALID"
    assert result.metadata["constraint"] == "require_estop_released"
    assert "robot.move" in node.required_permissions


def test_admission_rejects_weakened_registered_resource_lock(runtime_src):
    registry = CapabilityRegistry().load_skill_manifests(runtime_src / "system_skills")
    node = TaskNode.create(
        node_id="nav",
        task_graph_id="g_nav_resource_contract",
        user_goal_id="goal_nav_resource_contract",
        agent_id="agent",
        agent_name="app",
        app_id="app",
        session_id="sess",
        capability="robot.navigate_to",
        query_type=QueryType.ROBOT_CAPABILITY,
        params={"place": "kitchen"},
        resources=[ResourceRequest("base", mode="shared")],
    )
    graph = TaskGraph.create(
        task_graph_id="g_nav_resource_contract",
        user_goal_id="goal_nav_resource_contract",
        root_goal="navigate",
        agent_id="agent",
        app_id="app",
        session_id="sess",
        nodes={"nav": node},
    )

    result = AdmissionController(capability_registry=registry).admit(graph)

    assert result.success is False
    assert result.error_code == "SCHEDULER_CAPABILITY_CONTRACT_INVALID"
    assert result.metadata["resource_id"] == "base"
    assert result.metadata["mode"] == "shared"
