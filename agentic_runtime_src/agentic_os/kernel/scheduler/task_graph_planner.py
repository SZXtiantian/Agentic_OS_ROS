from __future__ import annotations

import json
import re
from typing import Any

from agentic_os.kernel.system_call import LLMQuery

from .admission import AdmissionController
from .audit import SchedulerAudit
from .errors import SchedulerError
from .models import stable_hash_payload
from .task_graph import TaskGraph


class TaskGraphPlanner:
    def __init__(self, *, kernel_service: Any, admission: AdmissionController | None = None, audit: SchedulerAudit | None = None, timeout_s: float = 60.0) -> None:
        self.kernel_service = kernel_service
        self.admission = admission or AdmissionController()
        self.audit = audit or SchedulerAudit()
        self.timeout_s = timeout_s

    def generate_task_graph(
        self,
        goal: str,
        *,
        agent_id: str,
        app_id: str,
        session_id: str,
        agent_name: str = "",
        user_goal_id: str = "",
    ) -> TaskGraph:
        query = LLMQuery(
            operation_type="scheduler_generate_task_graph",
            params={"goal_length": len(goal), "schema_id": "task_graph.schema.json"},
            messages=[
                {"role": "system", "content": _scheduler_system_prompt()},
                {
                    "role": "user",
                    "content": _build_goal_prompt(
                        goal,
                        agent_id=agent_id,
                        app_id=app_id,
                        session_id=session_id,
                        user_goal_id=user_goal_id,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            action_type="scheduler_planning",
            metadata={
                "agent_id": agent_id,
                "app_id": app_id,
                "session_id": session_id,
                "scheduler_component": "task_graph_planner",
                "permissions": ["llm.external.call"],
            },
        )
        self.audit.emit(
            "scheduler.llm.real_call_started",
            agent_id=agent_id,
            app_id=app_id,
            session_id=session_id,
            goal_id=user_goal_id,
            operation_type=query.operation_type,
            schema_id="task_graph.schema.json",
            success=True,
        )
        try:
            result = self.kernel_service.execute_request(agent_name or app_id, query, timeout_s=self.timeout_s)
        except Exception as exc:
            exception = _exception_summary(exc)
            self.audit.emit(
                "scheduler.llm.real_call_failed",
                success=False,
                error_code="SCHEDULER_LLM_REAL_PROVIDER_REQUIRED",
                agent_id=agent_id,
                app_id=app_id,
                session_id=session_id,
                goal_id=user_goal_id,
                operation_type=query.operation_type,
                schema_id="task_graph.schema.json",
                upstream_error_code="SCHEDULER_DISPATCH_FAILED",
                exception=exception,
            )
            raise SchedulerError(
                "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED",
                metadata={
                    "upstream_error_code": "SCHEDULER_DISPATCH_FAILED",
                    "exception": exception,
                },
            ) from exc
        if not result.success:
            syscall_id = getattr(getattr(result, "syscall", None), "syscall_id", "")
            self.audit.emit(
                "scheduler.llm.real_call_failed",
                success=False,
                error_code="SCHEDULER_LLM_REAL_PROVIDER_REQUIRED",
                agent_id=agent_id,
                app_id=app_id,
                session_id=session_id,
                goal_id=user_goal_id,
                syscall_id=syscall_id,
                operation_type=query.operation_type,
                schema_id="task_graph.schema.json",
                upstream_error_code=result.error_code,
            )
            raise SchedulerError(
                "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED",
                metadata={"upstream_error_code": result.error_code, "syscall_id": syscall_id},
            )
        try:
            payload = extract_llm_json_object(result.response)
            payload = _complete_authoritative_graph_envelope(
                payload,
                goal=goal,
                agent_id=agent_id,
                app_id=app_id,
                session_id=session_id,
                user_goal_id=user_goal_id,
            )
            payload_result = self.admission.validate_graph_payload_schema(payload)
            if not payload_result.success:
                raise ValueError(f"{payload_result.error_code}: {payload_result.message}")
            schema = self.admission._load_schema("task_graph.schema.json")
            graph = TaskGraph.from_dict(payload)
            graph.planner_call_syscall_id = result.syscall.syscall_id
            graph.planner_model = str(result.metadata.get("model") or "")
            graph.validated_schema_version = str(schema.get("$id") or "task_graph.schema.json")
            _validate_planner_identity(
                graph,
                goal=goal,
                agent_id=agent_id,
                app_id=app_id,
                session_id=session_id,
                user_goal_id=user_goal_id,
                admission=self.admission,
            )
            for admission_result in (
                self.admission.validate_no_low_level_robot_commands(graph),
                self.admission.validate_fact_provenance(graph),
            ):
                if not admission_result.success:
                    raise ValueError(f"{admission_result.error_code}: {admission_result.message}")
        except (SchedulerError, ValueError, TypeError) as exc:
            self.audit.emit(
                "scheduler.llm.real_call_failed",
                success=False,
                error_code="SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID",
                agent_id=agent_id,
                app_id=app_id,
                session_id=session_id,
                goal_id=user_goal_id,
                syscall_id=result.syscall.syscall_id,
            )
            metadata = {"syscall_id": result.syscall.syscall_id}
            if isinstance(exc, SchedulerError):
                metadata.update(exc.metadata)
            raise SchedulerError("SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID", str(exc), metadata) from exc
        self.audit.emit(
            "scheduler.llm.real_call_completed",
            agent_id=agent_id,
            app_id=app_id,
            session_id=session_id,
            goal_id=graph.user_goal_id,
            task_graph_id=graph.task_graph_id,
            syscall_id=result.syscall.syscall_id,
            success=True,
        )
        return graph


def extract_llm_json_object(response: Any) -> dict[str, Any]:
    if hasattr(response, "response_message"):
        response = response.response_message
    if hasattr(response, "data") and getattr(response, "data") is not None:
        response = response.data
    if isinstance(response, dict):
        return _extract_llm_mapping(response)
    if isinstance(response, str):
        try:
            parsed = json.loads(response)
            if isinstance(parsed, dict):
                return _extract_llm_mapping(parsed)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", response, flags=re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return _extract_llm_mapping(parsed)
    raise SchedulerError("SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID", metadata={"response_type": type(response).__name__})


def _extract_llm_mapping(payload: dict[str, Any], *, depth: int = 0) -> dict[str, Any]:
    if depth > 8:
        raise SchedulerError("SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID", metadata={"response_type": "nested_mapping"})
    if _looks_like_task_graph_payload(payload):
        return payload
    for key in ("task_graph", "graph", "taskGraph", "fusion_reasoning", "fusionReasoning"):
        value = payload.get(key)
        if isinstance(value, dict):
            return _extract_llm_mapping(value, depth=depth + 1)
    for key in ("json", "data", "response", "message", "content", "text"):
        value = payload.get(key)
        if isinstance(value, dict):
            return _extract_llm_mapping(value, depth=depth + 1)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return _extract_llm_mapping(parsed, depth=depth + 1)
    return payload


def _looks_like_task_graph_payload(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("nodes", "task_graph_id", "root_goal", "edges"))


def _validate_planner_identity(
    graph: TaskGraph,
    *,
    goal: str,
    agent_id: str,
    app_id: str,
    session_id: str,
    admission: AdmissionController,
    user_goal_id: str = "",
) -> None:
    expected = {
        "root_goal": goal,
        "agent_id": agent_id,
        "app_id": app_id,
        "session_id": session_id,
    }
    if user_goal_id:
        expected["user_goal_id"] = user_goal_id
    actual = {
        "root_goal": graph.root_goal,
        "agent_id": graph.agent_id,
        "app_id": graph.app_id,
        "session_id": graph.session_id,
    }
    if user_goal_id:
        actual["user_goal_id"] = graph.user_goal_id
    mismatches = {
        key: {"expected": expected[key], "actual": actual[key]}
        for key in expected
        if actual[key] != expected[key]
    }
    if mismatches:
        raise ValueError(f"planner graph identifiers changed: {json.dumps(mismatches, sort_keys=True, ensure_ascii=False)}")
    identity = admission.validate_graph_identity(graph)
    if not identity.success:
        raise ValueError(f"{identity.error_code}: {identity.message}")


def _complete_authoritative_graph_envelope(
    payload: dict[str, Any],
    *,
    goal: str,
    agent_id: str,
    app_id: str,
    session_id: str,
    user_goal_id: str = "",
) -> dict[str, Any]:
    completed = dict(payload)
    completed["task_graph_id"] = _authoritative_graph_id(
        goal=goal,
        agent_id=agent_id,
        app_id=app_id,
        session_id=session_id,
        user_goal_id=user_goal_id,
    )
    authoritative = {
        "root_goal": goal,
        "agent_id": agent_id,
        "app_id": app_id,
        "session_id": session_id,
    }
    if user_goal_id:
        authoritative["user_goal_id"] = user_goal_id
    for key, value in authoritative.items():
        completed[key] = value
    completed["status"] = "created"
    graph_id = str(completed.get("task_graph_id") or "")
    nodes = _canonical_nodes_payload(_node_collection_payload(completed))
    if nodes is not None:
        completed["nodes"] = nodes
    if completed.get("edges") is None:
        completed["edges"] = []
    if isinstance(completed.get("edges"), list):
        completed["edges"] = _canonical_edges_payload(completed["edges"])
    if isinstance(nodes, dict):
        for node_key, node_payload in nodes.items():
            if not isinstance(node_payload, dict):
                continue
            _complete_authoritative_node_payload(
                node_payload,
                node_id=str(node_key),
                graph_id=graph_id,
                agent_id=agent_id,
                app_id=app_id,
                session_id=session_id,
                user_goal_id=user_goal_id,
            )
    return completed


def _node_collection_payload(payload: dict[str, Any]) -> Any:
    for key in ("nodes", "task_nodes", "taskNodes", "tasks", "steps"):
        value = payload.get(key)
        if value is not None:
            return value
    if _looks_like_task_node_payload(payload):
        return [payload]
    return None


def _looks_like_task_node_payload(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("capability", "skill", "skill_name", "action", "operation_type", "query_type"))


def _complete_authoritative_node_payload(
    node_payload: dict[str, Any],
    *,
    node_id: str,
    graph_id: str,
    agent_id: str,
    app_id: str,
    session_id: str,
    user_goal_id: str = "",
) -> None:
    capability = _node_capability(node_payload)
    query_type = _node_query_type(node_payload, capability=capability)
    params = _node_params(node_payload, capability=capability)
    node_payload["node_id"] = node_id
    if graph_id:
        node_payload["task_graph_id"] = graph_id
    node_payload["agent_id"] = agent_id
    node_payload.setdefault("agent_name", app_id)
    node_payload["app_id"] = app_id
    node_payload["session_id"] = session_id
    if user_goal_id:
        node_payload["user_goal_id"] = user_goal_id
    node_payload["capability"] = capability
    node_payload["operation_type"] = _node_operation_type(node_payload, capability=capability, query_type=query_type)
    node_payload["query_type"] = query_type
    node_payload["params"] = params
    node_payload["metadata"] = _object_payload(node_payload.get("metadata"))
    node_payload["status"] = "created"
    node_payload["dependencies"] = _string_list_payload(node_payload.get("dependencies"))
    node_payload["dependents"] = _string_list_payload(node_payload.get("dependents"))
    node_payload["resources"] = _resource_list_payload(node_payload.get("resources"))
    node_payload["preconditions"] = _object_list_payload(node_payload.get("preconditions"))
    node_payload["required_permissions"] = _string_list_payload(node_payload.get("required_permissions"))
    node_payload["safety_constraints"] = _object_payload(node_payload.get("safety_constraints"))
    node_payload["produces_facts"] = _string_list_payload(node_payload.get("produces_facts"))
    node_payload["consumes_facts"] = _string_list_payload(node_payload.get("consumes_facts"))
    node_payload["resource_lease_ids"] = _string_list_payload(node_payload.get("resource_lease_ids"))
    node_payload["audit_ids"] = _string_list_payload(node_payload.get("audit_ids"))


def _node_capability(node_payload: dict[str, Any]) -> str:
    for key in ("capability", "skill_name", "skill", "action", "operation"):
        value = str(node_payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _node_query_type(node_payload: dict[str, Any], *, capability: str) -> str:
    raw_value = str(node_payload.get("query_type") or node_payload.get("lane") or node_payload.get("type") or "").strip()
    normalized = raw_value.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "robot": "robot_capability",
        "robot_capability": "robot_capability",
        "capability": "robot_capability",
        "skill_call": "skill",
        "skill": "skill",
        "tool": "tool",
        "llm": "llm",
        "memory": "memory",
        "storage": "storage",
        "context": "context",
        "human": "human",
    }
    if normalized in aliases:
        return aliases[normalized]
    if capability.startswith(("robot.", "arm.", "gripper.", "manipulation.", "perception.")):
        return "robot_capability"
    if capability.startswith(("memory.", "ctx.", "context.")):
        return "context" if capability.startswith(("ctx.", "context.")) else "memory"
    if capability.startswith("storage."):
        return "storage"
    if capability.startswith("human."):
        return "human"
    if capability.startswith("llm."):
        return "llm"
    return "skill"


def _node_operation_type(node_payload: dict[str, Any], *, capability: str, query_type: str) -> str:
    explicit = str(node_payload.get("operation_type") or "").strip()
    if explicit:
        return explicit
    for key in ("operation", "op"):
        value = str(node_payload.get(key) or "").strip()
        if value:
            if query_type == "skill" and value == capability:
                return "skill_call"
            return value
    if query_type == "skill" and capability:
        return "skill_call"
    return capability


def _node_params(node_payload: dict[str, Any], *, capability: str) -> dict[str, Any]:
    params = _object_payload(node_payload.get("params"))
    if capability == "report.say" and "message" not in params:
        for key in ("message", "text", "content"):
            value = node_payload.get(key)
            if isinstance(value, str) and value.strip():
                params["message"] = value
                break
    return params


def _object_payload(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _object_list_payload(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _resource_list_payload(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    resources: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            resources.append(dict(item))
        elif isinstance(item, str) and item.strip() and item.strip().lower() not in {"none", "n/a", "null"}:
            resources.append({"resource_id": item.strip()})
    return resources


def _string_list_payload(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item)]
    return []


def _authoritative_graph_id(*, goal: str, agent_id: str, app_id: str, session_id: str, user_goal_id: str = "") -> str:
    digest = stable_hash_payload(
        {
            "goal": goal,
            "agent_id": agent_id,
            "app_id": app_id,
            "session_id": session_id,
            "user_goal_id": user_goal_id,
        }
    )
    return f"graph_{digest[:32]}"


def _canonical_nodes_payload(nodes: Any) -> dict[str, Any] | None:
    if isinstance(nodes, dict):
        return dict(nodes)
    if not isinstance(nodes, list):
        return None
    canonical: dict[str, Any] = {}
    for index, node_payload in enumerate(nodes, start=1):
        if not isinstance(node_payload, dict):
            continue
        node_id = str(node_payload.get("node_id") or node_payload.get("id") or node_payload.get("name") or f"node_{index}")
        canonical[node_id] = dict(node_payload)
    return canonical


def _canonical_edges_payload(edges: list[Any]) -> list[Any]:
    canonical: list[Any] = []
    for index, edge_payload in enumerate(edges, start=1):
        if not isinstance(edge_payload, dict):
            canonical.append(edge_payload)
            continue
        edge = dict(edge_payload)
        source_id = str(edge.get("source_id") or edge.get("source") or "")
        target_id = str(edge.get("target_id") or edge.get("target") or "")
        if source_id and "source_id" not in edge:
            edge["source_id"] = source_id
        if target_id and "target_id" not in edge:
            edge["target_id"] = target_id
        if source_id and target_id:
            edge.setdefault("edge_id", f"edge_{source_id}_{target_id}_{index}")
            edge.setdefault("edge_type", "precedence")
        canonical.append(edge)
    return canonical


def _scheduler_system_prompt() -> str:
    return (
        "You are the AgenticOS scheduler planner. Return only JSON matching task_graph.schema.json. "
        "Return the TaskGraph object itself; do not wrap it under task_graph, graph, data, response, or text. "
        "Use high-level AgenticOS capabilities only, never low-level ROS2 topics, velocity commands, Nav2 calls, or MoveIt calls. "
        "The graph must be deterministic JSON with nodes as an object keyed by node_id and edges as an array. "
        "Every node must include node_id, task_graph_id, user_goal_id, agent_id, app_id, session_id, capability, operation_type, query_type, status, params, metadata, dependencies, dependents, resources, preconditions, required_permissions, safety_constraints, produces_facts, consumes_facts, resource_lease_ids, audit_ids. "
        "Allowed query_type values are llm, skill, robot_capability, tool, memory, storage, context, and human. "
        "For a safe reporting goal, use capability report.say with query_type skill and operation_type skill_call."
    )


def _build_goal_prompt(goal: str, *, agent_id: str, app_id: str, session_id: str, user_goal_id: str = "") -> str:
    goal_id_contract = user_goal_id or "non-empty string"
    return json.dumps(
        {
            "root_goal": goal,
            "required_identifiers": {
                "user_goal_id": goal_id_contract,
                "agent_id": agent_id,
                "app_id": app_id,
                "session_id": session_id,
            },
            "strict_top_level_required_keys": [
                "task_graph_id",
                "user_goal_id",
                "agent_id",
                "app_id",
                "session_id",
                "root_goal",
                "nodes",
                "edges",
                "status",
            ],
            "output_contract": {
                "task_graph_id": "non-empty string",
                "user_goal_id": goal_id_contract,
                "agent_id": agent_id,
                "app_id": app_id,
                "session_id": session_id,
                "root_goal": goal,
                "nodes": {
                    "node_id": {
                        "node_id": "same key",
                        "task_graph_id": "same graph id",
                        "user_goal_id": goal_id_contract,
                        "agent_id": agent_id,
                        "app_id": app_id,
                        "session_id": session_id,
                        "capability": "high-level AgenticOS capability",
                        "operation_type": "kernel operation",
                        "query_type": "skill",
                        "status": "created",
                        "params": {},
                        "metadata": {},
                        "dependencies": [],
                        "dependents": [],
                        "resources": [],
                        "preconditions": [],
                        "required_permissions": [],
                        "safety_constraints": {},
                        "produces_facts": [],
                        "consumes_facts": [],
                        "resource_lease_ids": [],
                        "audit_ids": [],
                    },
                },
                "edges": [],
                "status": "created",
            },
            "minimal_valid_example_for_safe_report_goal": {
                "task_graph_id": "graph_scheduler_verification_report",
                "user_goal_id": goal_id_contract,
                "agent_id": agent_id,
                "app_id": app_id,
                "session_id": session_id,
                "root_goal": goal,
                "nodes": {
                    "report": {
                        "node_id": "report",
                        "task_graph_id": "graph_scheduler_verification_report",
                        "user_goal_id": goal_id_contract,
                        "agent_id": agent_id,
                        "agent_name": app_id,
                        "app_id": app_id,
                        "session_id": session_id,
                        "capability": "report.say",
                        "operation_type": "skill_call",
                        "query_type": "skill",
                        "status": "created",
                        "params": {"message": "scheduler verification complete"},
                        "metadata": {},
                        "dependencies": [],
                        "dependents": [],
                        "resources": [],
                        "preconditions": [],
                        "required_permissions": [],
                        "safety_constraints": {},
                        "produces_facts": [],
                        "consumes_facts": [],
                        "resource_lease_ids": [],
                        "audit_ids": [],
                    }
                },
                "edges": [],
                "status": "created",
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _exception_summary(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    return {
        "type": type(exc).__name__,
        "message_sha256": stable_hash_payload(message),
        "message_length": len(message),
    }
