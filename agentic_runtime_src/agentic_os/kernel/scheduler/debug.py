from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from agentic_os.kernel.hooks import sanitize_event_payload

from .models import stable_hash_payload, utc_timestamp


_DEBUG_EXPORT_FAILED = "SCHEDULER_DEBUG_EXPORT_FAILED"
_SENSITIVE_DOT_TEXT_PARTS = (
    "api_key",
    "apikey",
    "bearer ",
    "token",
    "secret",
    "password",
    "prompt",
    "private",
    "message content",
    "messages",
    "memory",
)


class SchedulerDebugExporter:
    def __init__(self, *, schema_root: Path | None = None) -> None:
        self.schema_root = schema_root or Path(__file__).with_name("schemas")

    def snapshot(self, scheduler) -> dict[str, Any]:
        try:
            resource_snapshot = scheduler.resource_arbiter.snapshot()
            environment_snapshot = scheduler.environment_store.snapshot()
            graph_counts = scheduler.graph_store.global_dag.counts()
            snapshot = {
                "schema_version": "debug_snapshot.schema.json",
                "generated_at": utc_timestamp(),
                "success": True,
                "error_code": "",
                "message": "",
                "scheduler_policy": scheduler.policy,
                "global_revision": scheduler.graph_store.revision,
                "graphs": {graph_id: _safe_graph_dict(graph) for graph_id, graph in sorted(scheduler.graph_store.global_dag.graphs.items())},
                "nodes_by_status": graph_counts,
                "ready_queue": scheduler.ready_queue.snapshot(),
                "running_nodes": sorted(scheduler.graph_store.global_dag.running_set),
                "blocked_nodes": sorted(scheduler.graph_store.global_dag.blocked_set),
                "completed_nodes": sorted(scheduler.graph_store.global_dag.completed_set),
                "failed_nodes": sorted(scheduler.graph_store.global_dag.failed_set),
                "leases": [_safe_lease_dict(item) for item in resource_snapshot["leases"].values()],
                "expired_leases": [_safe_lease_dict(item) for item in resource_snapshot["expired_leases"].values()],
                "facts": [_safe_fact_dict(item) for item in environment_snapshot["facts"].values()],
                "expired_facts": [_safe_fact_dict(item) for item in environment_snapshot["expired_facts"].values()],
                "opportunity_windows": scheduler.opportunity_index.snapshot(),
                "fusion_plans": [_safe_fusion_plan_dict(item) for item in scheduler.fusion_engine.snapshot()],
                "recent_audit_event_ids": scheduler.audit.recent_ids(),
                "recent_kernel_event_ids": [event.get("event_id", "") for event in scheduler.event_sink.recent(limit=25)] if scheduler.event_sink is not None else [],
                "provider_status_summary": scheduler.provider_status_summary(),
            }
            snapshot = sanitize_event_payload(snapshot)
            self._validate(snapshot)
            scheduler.audit.emit("scheduler.debug.snapshot_exported", success=True)
            return snapshot
        except Exception as exc:
            audit_id = _emit_debug_audit(
                scheduler,
                "scheduler.debug.snapshot_exported",
                success=False,
                error_code=_DEBUG_EXPORT_FAILED,
                failure=_failure_details(exc),
            )
            snapshot = _failure_snapshot(scheduler, exc, audit_id=audit_id)
            try:
                self._validate(snapshot)
            except Exception:
                pass
            return snapshot

    def export_dot(self, scheduler, task_graph_id: str | None = None) -> str:
        try:
            graphs = scheduler.graph_store.global_dag.graphs
            selected = [graphs[task_graph_id]] if task_graph_id else list(graphs.values())
            lines = ["digraph AgenticScheduler {", '  rankdir="LR";']
            for graph in selected:
                lines.append(f'  subgraph "cluster_{_dot(graph.task_graph_id)}" {{')
                lines.append(f'    label="{_dot(graph.task_graph_id)}";')
                for node in graph.nodes.values():
                    label = "\\n".join(_dot_label_lines(node))
                    style = _node_style(node.status)
                    lines.append(f'    "{_dot(node.node_id)}" [label="{label}", {style}];')
                for edge in graph.edges:
                    attrs = []
                    if edge.edge_type == "reuses_fact":
                        attrs.extend(['style="dashed"', f'label="{_dot(edge.fact_key)}"'])
                    elif edge.edge_type == "safety_block":
                        attrs.extend(['style="dashed"', 'color="red"'])
                    elif edge.edge_type in {"produces_fact", "consumes_fact"}:
                        label = edge.edge_type if not edge.fact_key else f"{edge.edge_type}:{edge.fact_key}"
                        attrs.extend(['style="dotted"', f'label="{_dot(label)}"'])
                    elif edge.edge_type != "precedence":
                        attrs.append('style="dotted"')
                    attr_text = f" [{', '.join(attrs)}]" if attrs else ""
                    lines.append(f'    "{_dot(edge.source_id)}" -> "{_dot(edge.target_id)}"{attr_text};')
                lines.append("  }")
            lines.append("}")
            dot_text = "\n".join(lines)
            scheduler.audit.emit("scheduler.debug.dot_exported", success=True, task_graph_id=task_graph_id or "")
            return dot_text
        except Exception as exc:
            _emit_debug_audit(
                scheduler,
                "scheduler.debug.dot_exported",
                success=False,
                error_code=_DEBUG_EXPORT_FAILED,
                task_graph_id=task_graph_id or "",
                failure=_failure_details(exc),
            )
            return _failure_dot(exc)

    def _validate(self, snapshot: dict[str, Any]) -> None:
        schema = json.loads((self.schema_root / "debug_snapshot.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(snapshot)


def _dot(value: Any) -> str:
    return _safe_dot_text(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _safe_dot_text(value: Any) -> str:
    text = str(value)
    lowered = text.lower()
    if any(part in lowered for part in _SENSITIVE_DOT_TEXT_PARTS):
        return f"[REDACTED:{stable_hash_payload(text)[:12]}]"
    return text


def _node_style(status: str) -> str:
    if status == "ready":
        return 'color="blue", style="bold"'
    if status == "running":
        return 'style="filled", fillcolor="orange"'
    if status == "completed":
        return 'style="filled", fillcolor="green"'
    if status in {"failed", "rejected"}:
        return 'style="filled", fillcolor="red"'
    if status == "blocked":
        return 'style="filled", fillcolor="gray"'
    return 'color="black"'


def _dot_label_lines(node) -> list[str]:
    lines = [
        _dot(node.node_id),
        _dot(node.status),
        _dot(node.lane),
        _dot(node.agent_id),
        _dot(node.capability),
        f"leases={len(node.resource_lease_ids)}",
    ]
    if node.error_code:
        lines.append(f"error={_dot(node.error_code)}")
    produced = _node_produced_facts(node)
    if produced:
        lines.append(f"produces={_dot(','.join(produced))}")
    consumed = _node_consumed_facts(node)
    if consumed:
        lines.append(f"consumes={_dot(','.join(consumed))}")
    if node.fusion_group_id:
        lines.append(f"fusion={_dot(node.fusion_group_id)}")
    return lines


def _node_produced_facts(node) -> list[str]:
    facts = list(getattr(node, "produces_facts", []) or [])
    facts.extend(_fact_keys_from_specs(getattr(node, "metadata", {}).get("produces_fact_specs")))
    return _unique_nonempty(facts)


def _node_consumed_facts(node) -> list[str]:
    facts = list(getattr(node, "consumes_facts", []) or [])
    facts.extend(_fact_keys_from_specs(getattr(node, "metadata", {}).get("consumes_fact_specs")))
    for precondition in getattr(node, "preconditions", []) or []:
        facts.append(str(getattr(precondition, "fact_key", "") or ""))
    return _unique_nonempty(facts)


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


def _emit_debug_audit(scheduler, event_type: str, **metadata: Any) -> str:
    try:
        return str(scheduler.audit.emit(event_type, **metadata))
    except Exception:
        return ""


def _failure_snapshot(scheduler, exc: Exception, *, audit_id: str = "") -> dict[str, Any]:
    snapshot = {
        "schema_version": "debug_snapshot.schema.json",
        "generated_at": utc_timestamp(),
        "success": False,
        "error_code": _DEBUG_EXPORT_FAILED,
        "message": "debug snapshot export failed",
        "scheduler_policy": _safe_scheduler_policy(scheduler),
        "global_revision": _safe_global_revision(scheduler),
        "graphs": {},
        "nodes_by_status": {},
        "ready_queue": [],
        "running_nodes": [],
        "blocked_nodes": [],
        "completed_nodes": [],
        "failed_nodes": [],
        "leases": [],
        "expired_leases": [],
        "facts": [],
        "expired_facts": [],
        "opportunity_windows": [],
        "fusion_plans": [],
        "recent_audit_event_ids": _safe_recent_audit_ids(scheduler, audit_id),
        "recent_kernel_event_ids": _safe_recent_kernel_event_ids(scheduler),
        "provider_status_summary": {
            "state": "unavailable",
            "error_code": _DEBUG_EXPORT_FAILED,
            "failure": _failure_details(exc),
        },
    }
    return sanitize_event_payload(snapshot)


def _failure_dot(exc: Exception) -> str:
    label = "\\n".join([_DEBUG_EXPORT_FAILED, _dot(type(exc).__name__)])
    return "\n".join(
        [
            "digraph AgenticScheduler {",
            '  rankdir="LR";',
            f'  "{_DEBUG_EXPORT_FAILED}" [label="{label}", style="filled", fillcolor="red"];',
            "}",
        ]
    )


def _failure_details(exc: Exception) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message_summary": _summary(str(exc)),
    }


def _safe_scheduler_policy(scheduler) -> str:
    try:
        return str(getattr(scheduler, "policy", ""))
    except Exception:
        return ""


def _safe_global_revision(scheduler) -> int:
    try:
        return int(scheduler.graph_store.revision)
    except Exception:
        return 0


def _safe_recent_audit_ids(scheduler, audit_id: str) -> list[str]:
    try:
        ids = scheduler.audit.recent_ids()
    except Exception:
        ids = []
    if audit_id and audit_id not in ids:
        ids.append(audit_id)
    return ids


def _safe_recent_kernel_event_ids(scheduler) -> list[str]:
    try:
        if scheduler.event_sink is None:
            return []
        return [event.get("event_id", "") for event in scheduler.event_sink.recent(limit=25)]
    except Exception:
        return []


def _safe_graph_dict(graph) -> dict[str, Any]:
    payload = graph.to_dict()
    root_goal = str(payload.get("root_goal") or "")
    payload["root_goal"] = _summary(root_goal)
    for node in payload.get("nodes", {}).values():
        if not isinstance(node, dict):
            continue
        node["params"] = _summary(node.get("params", {}))
        node["metadata"] = sanitize_event_payload(node.get("metadata", {}))
        if node.get("result") is not None:
            node["result"] = _summary(node.get("result"))
    return sanitize_event_payload(payload)


def _safe_fact_dict(fact: dict[str, Any]) -> dict[str, Any]:
    payload = dict(fact)
    payload["value"] = _summary(payload.get("value"))
    payload["metadata"] = sanitize_event_payload(payload.get("metadata", {}))
    return sanitize_event_payload(payload)


def _safe_lease_dict(lease: dict[str, Any]) -> dict[str, Any]:
    payload = dict(lease)
    handle_id = str(payload.pop("agent_resource_handle_id", "") or "")
    if handle_id:
        payload["agent_resource_handle_summary"] = _opaque_summary(handle_id)
    payload["lease_info_summary"] = _opaque_summary(sanitize_event_payload(payload.pop("metadata", {})))
    return sanitize_event_payload(payload)


def _safe_fusion_plan_dict(plan: dict[str, Any]) -> dict[str, Any]:
    payload = dict(plan)
    payload["audit_summary"] = _summary(payload.get("audit_metadata", {}))
    payload["audit_metadata"] = sanitize_event_payload(payload.get("audit_metadata", {}))
    return sanitize_event_payload(payload)


def _summary(value: Any) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value)
    else:
        keys = []
    return {
        "sha256": stable_hash_payload(value),
        "length": len(text),
        "keys": keys,
    }


def _opaque_summary(value: Any) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "sha256": stable_hash_payload(value),
        "length": len(text),
    }
