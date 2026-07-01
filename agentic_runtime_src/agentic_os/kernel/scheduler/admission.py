from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .errors import SchedulerResult
from .models import QueryType, TaskNodeStatus
from .resources import ResourceRequest
from .task_graph import TaskGraph
from .task_node import TaskNode


LOW_LEVEL_ROBOT_MARKERS = {
    "/" + "cmd_vel",
    "rclpy",
    "nav2 action",
    "nav2_msgs/action",
    "/navigate_to_pose",
    "moveit action",
    "moveit_msgs/",
    "geometry_msgs/twist",
    "joint_effort",
    "joint_velocity",
    "trajectory_msgs/",
    "wheel_velocity",
}

DIRECT_ROBOT_INTERFACE_PREFIXES = ("nav2.", "moveit.", "ros2.", "rclpy.")
DIRECT_ROBOT_INTERFACE_NAMES = {
    "/" + "cmd_vel",
    "/navigate_to_pose",
    "cmd_vel",
    "navigate_to_pose",
    "nav2_msgs/action/navigatetopose",
    "moveit_msgs/action/movegroup",
}

PROTECTED_CAPABILITY_PREFIXES = ("robot.", "arm.", "gripper.", "manipulation.", "perception.")
READ_ONLY_CAPABILITY_SUFFIXES = (".get_state", ".state", ".status")
RESOURCE_OPTIONAL_CAPABILITIES = {"robot.stop", "robot.get_state", "arm.get_state"}
PHYSICAL_WORLD_FACT_KEYS = {"cup_pose", "object_pose", "robot_pose", "held_object", "held_object_pose"}


@dataclass
class AdmissionResult:
    success: bool
    error_code: str = ""
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_scheduler_result(self) -> SchedulerResult:
        if self.success:
            return SchedulerResult.ok(**self.metadata)
        return SchedulerResult.error(self.error_code, self.message, **self.metadata)


class AdmissionController:
    def __init__(self, *, schema_root: Path | None = None, capability_registry: Any | None = None) -> None:
        self.schema_root = schema_root or Path(__file__).with_name("schemas")
        self.capability_registry = capability_registry

    def admit(self, graph: TaskGraph) -> AdmissionResult:
        schema_result = self.validate_graph_schema(graph)
        if not schema_result.success:
            return schema_result
        identity_result = self.validate_graph_identity(graph)
        if not identity_result.success:
            return identity_result
        contract_result = self.validate_capability_contracts(graph)
        if not contract_result.success:
            return contract_result
        command_result = self.validate_no_low_level_robot_commands(graph)
        if not command_result.success:
            return command_result
        fact_result = self.validate_fact_provenance(graph)
        if not fact_result.success:
            return fact_result
        for node in graph.nodes.values():
            node.status = TaskNodeStatus.ADMITTED
        return AdmissionResult(True)

    def validate_graph_identity(self, graph: TaskGraph) -> AdmissionResult:
        for node_key, node in graph.nodes.items():
            mismatches = {
                field_name: {"graph": graph_value, "node": node_value}
                for field_name, graph_value, node_value in (
                    ("task_graph_id", graph.task_graph_id, node.task_graph_id),
                    ("user_goal_id", graph.user_goal_id, node.user_goal_id),
                    ("agent_id", graph.agent_id, node.agent_id),
                    ("app_id", graph.app_id, node.app_id),
                    ("session_id", graph.session_id, node.session_id),
                )
                if graph_value != node_value
            }
            if node.node_id != node_key:
                mismatches["node_id"] = {"graph_key": node_key, "node": node.node_id}
            if mismatches:
                return AdmissionResult(
                    False,
                    "SCHEDULER_GRAPH_SCHEMA_INVALID",
                    "task graph and node identifiers must match",
                    {"task_graph_id": graph.task_graph_id, "node_id": node.node_id, "mismatches": mismatches},
                )
        node_ids = set(graph.nodes)
        for edge in graph.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                return AdmissionResult(
                    False,
                    "SCHEDULER_GRAPH_SCHEMA_INVALID",
                    "edge endpoint is not present in graph nodes",
                    {"task_graph_id": graph.task_graph_id, "edge_id": edge.edge_id, "source_id": edge.source_id, "target_id": edge.target_id},
                )
        return AdmissionResult(True)

    def validate_graph_schema(self, graph: TaskGraph) -> AdmissionResult:
        return self.validate_graph_payload_schema(graph.to_dict(), task_graph_id=graph.task_graph_id)

    def validate_graph_payload_schema(self, payload: dict[str, Any], *, task_graph_id: str | None = None) -> AdmissionResult:
        graph_id = str(task_graph_id or payload.get("task_graph_id") or "")
        try:
            schema = self._load_schema("task_graph.schema.json")
            Draft202012Validator(schema).validate(payload)
            for node_key, raw_node in dict(payload.get("nodes") or {}).items():
                if not isinstance(raw_node, dict):
                    return AdmissionResult(
                        False,
                        "SCHEDULER_NODE_SCHEMA_INVALID",
                        "task graph node payload must be an object",
                        {"task_graph_id": graph_id, "node_key": str(node_key)},
                    )
                node_result = self.validate_node_schema(raw_node)
                if not node_result.success:
                    node_result.metadata.setdefault("task_graph_id", graph_id)
                    node_result.metadata.setdefault("node_key", str(node_key))
                    return node_result
            json_result = _validate_json_serializable_payload(
                payload,
                error_code="SCHEDULER_GRAPH_SCHEMA_INVALID",
                metadata={"task_graph_id": graph_id},
            )
            if not json_result.success:
                return json_result
        except (ValidationError, OSError, json.JSONDecodeError) as exc:
            return AdmissionResult(False, "SCHEDULER_GRAPH_SCHEMA_INVALID", str(exc), {"task_graph_id": graph_id})
        return AdmissionResult(True)

    def validate_node_schema(self, node_payload: dict[str, Any]) -> AdmissionResult:
        json_result = _validate_json_serializable_payload(
            node_payload,
            error_code="SCHEDULER_NODE_SCHEMA_INVALID",
            metadata={"node_id": node_payload.get("node_id")},
        )
        if not json_result.success:
            return json_result
        try:
            schema = self._load_schema("task_node.schema.json")
            Draft202012Validator(schema).validate(node_payload)
        except (ValidationError, OSError, json.JSONDecodeError) as exc:
            return AdmissionResult(False, "SCHEDULER_NODE_SCHEMA_INVALID", str(exc), {"node_id": node_payload.get("node_id")})
        return AdmissionResult(True)

    def validate_capability_contracts(self, graph: TaskGraph) -> AdmissionResult:
        for node in graph.nodes.values():
            if node.query_type not in QueryType.ALL:
                return AdmissionResult(False, "SCHEDULER_CAPABILITY_CONTRACT_INVALID", "unsupported query_type", {"node_id": node.node_id})
            if node.query_type in {QueryType.SKILL, QueryType.ROBOT_CAPABILITY, QueryType.HUMAN} and not node.capability:
                return AdmissionResult(False, "SCHEDULER_CAPABILITY_CONTRACT_INVALID", "capability is required", {"node_id": node.node_id})
            if self.capability_registry is not None and node.query_type in {QueryType.SKILL, QueryType.ROBOT_CAPABILITY, QueryType.HUMAN}:
                try:
                    spec = self.capability_registry.get(node.capability)
                except Exception:
                    spec = None
                if spec is None:
                    return AdmissionResult(
                        False,
                        "SCHEDULER_CAPABILITY_UNAVAILABLE",
                        "capability is not registered",
                        {"node_id": node.node_id, "capability": node.capability},
                    )
                enrich_result = self._apply_capability_contract(node, spec)
                if not enrich_result.success:
                    return enrich_result
                runtime_contract_result = self._validate_runtime_capability_contract(node, spec)
                if not runtime_contract_result.success:
                    return runtime_contract_result
        return AdmissionResult(True)

    def validate_no_low_level_robot_commands(self, graph: TaskGraph) -> AdmissionResult:
        for node in graph.nodes.values():
            for field_name, raw_value in (("capability", node.capability), ("operation_type", node.operation_type)):
                value = str(raw_value or "").strip().lower()
                if _is_direct_robot_interface_label(value):
                    return AdmissionResult(
                        False,
                        "SCHEDULER_ADMISSION_REJECTED",
                        "direct robot middleware interface rejected",
                        {
                            "task_graph_id": graph.task_graph_id,
                            "node_id": node.node_id,
                            "field": field_name,
                            "value": value,
                        },
                    )
        payload = json.dumps(graph.to_dict(), ensure_ascii=False, default=str).lower()
        for marker in LOW_LEVEL_ROBOT_MARKERS:
            if marker in payload:
                return AdmissionResult(
                    False,
                    "SCHEDULER_ADMISSION_REJECTED",
                    "low-level robot command marker rejected",
                    {"marker": marker, "task_graph_id": graph.task_graph_id},
                )
        return AdmissionResult(True)

    def validate_fact_provenance(self, graph: TaskGraph) -> AdmissionResult:
        for node in graph.nodes.values():
            if node.query_type != QueryType.LLM:
                continue
            produced_fact_keys = _node_produced_fact_keys(node)
            physical_fact_keys = sorted(fact_key for fact_key in produced_fact_keys if _is_physical_world_fact_key(fact_key))
            if physical_fact_keys:
                return AdmissionResult(
                    False,
                    "SCHEDULER_FACT_SOURCE_UNVERIFIED",
                    "LLM nodes cannot produce physical environment facts",
                    {"task_graph_id": graph.task_graph_id, "node_id": node.node_id, "fact_keys": physical_fact_keys},
                )
            if node.metadata.get("produces_fact_specs"):
                return AdmissionResult(
                    False,
                    "SCHEDULER_FACT_SOURCE_UNVERIFIED",
                    "LLM nodes cannot declare environment fact extraction specs",
                    {"task_graph_id": graph.task_graph_id, "node_id": node.node_id},
                )
        return AdmissionResult(True)

    def _load_schema(self, name: str) -> dict[str, Any]:
        return json.loads((self.schema_root / name).read_text(encoding="utf-8"))

    def _apply_capability_contract(self, node: TaskNode, spec: Any) -> AdmissionResult:
        input_schema = dict(getattr(spec, "input_schema", {}) or {})
        if input_schema:
            params_result = self._validate_params(node, input_schema)
            if not params_result.success:
                return params_result
        for permission in list(getattr(spec, "permissions", []) or []):
            permission_key = str(permission)
            if permission_key and permission_key not in node.required_permissions:
                node.required_permissions.append(permission_key)
        for key, value in dict(getattr(spec, "safety_constraints", {}) or {}).items():
            if key in node.safety_constraints and node.safety_constraints[key] != value:
                return AdmissionResult(
                    False,
                    "SCHEDULER_CAPABILITY_CONTRACT_INVALID",
                    "node safety constraint conflicts with capability contract",
                    {
                        "node_id": node.node_id,
                        "capability": node.capability,
                        "constraint": str(key),
                        "expected": value,
                        "actual": node.safety_constraints[key],
                    },
                )
            node.safety_constraints[key] = value
        existing_resources = {request.resource_id: request for request in node.resources}
        for resource_id in list(getattr(spec, "resource_locks", []) or []):
            resource_key = str(resource_id)
            if not resource_key:
                continue
            existing = existing_resources.get(resource_key)
            if existing is not None:
                if existing.mode != "exclusive":
                    return AdmissionResult(
                        False,
                        "SCHEDULER_CAPABILITY_CONTRACT_INVALID",
                        "capability resource lock must be exclusive",
                        {"node_id": node.node_id, "capability": node.capability, "resource_id": resource_key, "mode": existing.mode},
                    )
                continue
            if resource_key:
                node.resources.append(
                    ResourceRequest(
                        resource_id=resource_key,
                        mode="exclusive",
                        reason=f"capability_contract:{getattr(spec, 'name', node.capability)}",
                    )
                )
                existing_resources[resource_key] = node.resources[-1]
        if not node.input_schema_id and input_schema:
            node.input_schema_id = f"capability:{getattr(spec, 'name', node.capability)}:input"
        if not node.output_schema_id and getattr(spec, "output_schema", None):
            node.output_schema_id = f"capability:{getattr(spec, 'name', node.capability)}:output"
        return AdmissionResult(True)

    def _validate_runtime_capability_contract(self, node: TaskNode, spec: Any) -> AdmissionResult:
        if node.query_type != QueryType.ROBOT_CAPABILITY or not _is_protected_capability(node.capability):
            return AdmissionResult(True)
        if not node.required_permissions:
            return _contract_missing(node, "permissions", "protected robot capability requires permissions")
        if not node.safety_constraints:
            return _contract_missing(node, "safety_constraints", "protected robot capability requires safety constraints")
        if _requires_resource_lock(node.capability) and not node.resources:
            return _contract_missing(node, "resource_locks", "protected robot capability requires resource locks")
        observability = dict(getattr(spec, "observability", {}) or {})
        if not observability.get("audit", False):
            return _contract_missing(node, "observability.audit", "protected robot capability requires audit observability")
        return AdmissionResult(True)

    def _validate_params(self, node: TaskNode, input_schema: dict[str, Any]) -> AdmissionResult:
        payload = _effective_call_args(node.params)
        try:
            Draft202012Validator(input_schema).validate(payload)
        except ValidationError as exc:
            return AdmissionResult(
                False,
                "SCHEDULER_CAPABILITY_CONTRACT_INVALID",
                "node params do not satisfy capability input_schema",
                {
                    "node_id": node.node_id,
                    "capability": node.capability,
                    "validation_error": exc.message,
                    "schema_path": [str(part) for part in exc.schema_path],
                },
            )
        return AdmissionResult(True)


def _effective_call_args(params: dict[str, Any]) -> dict[str, Any]:
    for wrapper_key in ("args", "parameters"):
        wrapped = params.get(wrapper_key)
        if isinstance(wrapped, dict):
            return dict(wrapped)
    return dict(params)


def _validate_json_serializable_payload(payload: Any, *, error_code: str, metadata: dict[str, Any]) -> AdmissionResult:
    invalid = _find_non_json_value(payload)
    if invalid is not None:
        path, value_type = invalid
        return AdmissionResult(
            False,
            error_code,
            "scheduler graph payload must be JSON serializable",
            {**metadata, "json_path": path, "json_value_type": value_type},
        )
    try:
        json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        return AdmissionResult(
            False,
            error_code,
            "scheduler graph payload must be JSON serializable",
            {**metadata, "json_error": str(exc)},
        )
    return AdmissionResult(True)


def _find_non_json_value(value: Any, path: str = "$") -> tuple[str, str] | None:
    if value is None or isinstance(value, (str, bool, int)):
        return None
    if isinstance(value, float):
        if math.isfinite(value):
            return None
        return path, "non_finite_float"
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return f"{path}[{type(key).__name__}]", "non_string_key"
            child = _find_non_json_value(item, _json_child_path(path, key))
            if child is not None:
                return child
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            child = _find_non_json_value(item, f"{path}[{index}]")
            if child is not None:
                return child
        return None
    return path, type(value).__name__


def _json_child_path(path: str, key: str) -> str:
    if key.replace("_", "").isalnum():
        return f"{path}.{key}"
    return f"{path}[{key!r}]"


def _is_direct_robot_interface_label(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return False
    if normalized in DIRECT_ROBOT_INTERFACE_NAMES:
        return True
    return normalized.startswith(DIRECT_ROBOT_INTERFACE_PREFIXES)


def _is_protected_capability(capability: str) -> bool:
    return str(capability or "").startswith(PROTECTED_CAPABILITY_PREFIXES)


def _requires_resource_lock(capability: str) -> bool:
    normalized = str(capability or "")
    if normalized in RESOURCE_OPTIONAL_CAPABILITIES:
        return False
    return not normalized.endswith(READ_ONLY_CAPABILITY_SUFFIXES)


def _node_produced_fact_keys(node: TaskNode) -> set[str]:
    fact_keys = {str(fact_key) for fact_key in list(node.produces_facts or []) if str(fact_key)}
    specs = node.metadata.get("produces_fact_specs")
    if isinstance(specs, list):
        for spec in specs:
            if isinstance(spec, dict):
                fact_key = str(spec.get("fact_key") or spec.get("key") or "")
                if fact_key:
                    fact_keys.add(fact_key)
    return fact_keys


def _is_physical_world_fact_key(fact_key: str) -> bool:
    normalized = str(fact_key or "").strip().lower()
    return normalized in PHYSICAL_WORLD_FACT_KEYS or normalized.endswith("_pose")


def _contract_missing(node: TaskNode, field: str, message: str) -> AdmissionResult:
    return AdmissionResult(
        False,
        "SCHEDULER_CAPABILITY_CONTRACT_INVALID",
        message,
        {"node_id": node.node_id, "capability": node.capability, "missing_contract_field": field},
    )
