from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentic_os.kernel.system_call import RobotCapabilityQuery

from .audit import SchedulerAudit
from .models import PreemptPolicy
from .task_node import TaskNode


@dataclass
class PreemptionResult:
    success: bool
    error_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class PreemptionManager:
    def __init__(self, *, kernel_service=None, audit: SchedulerAudit | None = None) -> None:
        self.kernel_service = kernel_service
        self.audit = audit or SchedulerAudit()

    def request_preemption(self, node: TaskNode, *, reason: str) -> PreemptionResult:
        self.audit.emit("scheduler.preemption.requested", **_preemption_metadata(node, reason=reason))
        if node.preempt_policy == PreemptPolicy.EMERGENCY_STOP_ONLY:
            if _is_emergency_reason(reason):
                return self._dispatch_emergency_stop(node, reason=reason)
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
                **_preemption_metadata(node, reason=reason),
            )
            return PreemptionResult(False, "SCHEDULER_PREEMPTION_UNSUPPORTED")
        if node.preempt_policy == PreemptPolicy.NON_PREEMPTIBLE:
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
                **_preemption_metadata(node, reason=reason),
            )
            return PreemptionResult(False, "SCHEDULER_PREEMPTION_UNSUPPORTED")
        if node.preempt_policy == PreemptPolicy.CHECKPOINTABLE:
            return self._checkpoint_preemption(node, reason=reason)
        if self.kernel_service is None or not node.syscall_id:
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
                **_preemption_metadata(node, reason="no cancellable syscall"),
            )
            return PreemptionResult(False, "SCHEDULER_PREEMPTION_UNSUPPORTED")
        response = self.kernel_service.cancel_request(node.syscall_id)
        if response.success:
            self.audit.emit("scheduler.preemption.accepted", **_preemption_metadata(node, reason=reason))
            return PreemptionResult(True, metadata={"syscall_id": node.syscall_id})
        self.audit.emit(
            "scheduler.preemption.rejected",
            success=False,
            error_code=response.error_code or "SCHEDULER_PREEMPTION_UNSUPPORTED",
            **_preemption_metadata(node, reason=reason),
        )
        return PreemptionResult(False, response.error_code or "SCHEDULER_PREEMPTION_UNSUPPORTED")

    def _dispatch_emergency_stop(self, node: TaskNode, *, reason: str) -> PreemptionResult:
        if self.kernel_service is None:
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
                **_preemption_metadata(node, reason="kernel service unavailable for emergency stop"),
            )
            return PreemptionResult(False, "SCHEDULER_PREEMPTION_UNSUPPORTED")
        self.audit.emit(
            "scheduler.safety.interrupt",
            agent_id=node.agent_id,
            app_id=node.app_id,
            session_id=node.session_id,
            task_graph_id=node.task_graph_id,
            node_id=node.node_id,
            syscall_id=node.syscall_id,
            reason=reason,
        )
        query = RobotCapabilityQuery(
            operation_type="robot.stop",
            params={"reason": reason, "preempted_node_id": node.node_id, "preempted_syscall_id": node.syscall_id},
            skill_name="robot.stop",
            app_id=node.app_id,
            session_id=node.session_id,
            metadata={
                **dict(node.metadata),
                "agent_id": node.agent_id,
                "app_id": node.app_id,
                "session_id": node.session_id,
                "permissions": list(node.required_permissions),
                "task_graph_id": node.task_graph_id,
                "node_id": node.node_id,
                "scheduler_component": "environment_aware_dag",
                "scheduler_preemption": "emergency_stop_only",
            },
        )
        result = self.kernel_service.execute_request(node.agent_name or node.app_id, query, timeout_s=5.0)
        if result.success:
            self.audit.emit(
                "scheduler.preemption.accepted",
                **_preemption_metadata(node, reason=reason),
                emergency_stop_syscall_id=result.syscall.syscall_id,
            )
            return PreemptionResult(True, metadata={"syscall_id": node.syscall_id, "emergency_stop_syscall_id": result.syscall.syscall_id})
        self.audit.emit(
            "scheduler.preemption.rejected",
            success=False,
            error_code=result.error_code or "SCHEDULER_PREEMPTION_UNSUPPORTED",
            **_preemption_metadata(node, reason=reason),
        )
        return PreemptionResult(False, result.error_code or "SCHEDULER_PREEMPTION_UNSUPPORTED")

    def _checkpoint_preemption(self, node: TaskNode, *, reason: str) -> PreemptionResult:
        if self.kernel_service is None or not node.syscall_id:
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
                **_preemption_metadata(node, reason="no checkpointable syscall"),
            )
            return PreemptionResult(False, "SCHEDULER_PREEMPTION_UNSUPPORTED")

        checkpoint_request = getattr(self.kernel_service, "checkpoint_request", None)
        if not callable(checkpoint_request):
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
                **_preemption_metadata(node, reason="checkpoint preemption unsupported by kernel service"),
            )
            return PreemptionResult(False, "SCHEDULER_PREEMPTION_UNSUPPORTED")

        try:
            response = _call_checkpoint_request(checkpoint_request, node, reason=reason)
        except TimeoutError as exc:
            timeout_reason = str(exc) or "checkpoint preemption timed out"
            self.audit.emit(
                "scheduler.preemption.timeout",
                success=False,
                error_code="SCHEDULER_PREEMPTION_TIMEOUT",
                **_preemption_metadata(node, reason=timeout_reason),
            )
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_TIMEOUT",
                **_preemption_metadata(node, reason=timeout_reason),
            )
            return PreemptionResult(False, "SCHEDULER_PREEMPTION_TIMEOUT")

        if not _response_success(response):
            error_code = _response_error_code(response) or "SCHEDULER_PREEMPTION_UNSUPPORTED"
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code=error_code,
                **_preemption_metadata(node, reason=reason),
            )
            return PreemptionResult(False, error_code)

        checkpoint = _extract_checkpoint_payload(node, response)
        if not checkpoint:
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
                **_preemption_metadata(node, reason="checkpoint response did not include preserved progress"),
            )
            return PreemptionResult(False, "SCHEDULER_PREEMPTION_UNSUPPORTED")

        node.metadata["checkpoint"] = checkpoint
        checkpoints = list(node.metadata.get("checkpoints") or [])
        checkpoints.append(checkpoint)
        node.metadata["checkpoints"] = checkpoints
        result = dict(node.result or {})
        result["checkpoint"] = checkpoint
        node.result = result

        self.audit.emit(
            "scheduler.preemption.accepted",
            **_preemption_metadata(node, reason=reason),
            checkpoint_saved=True,
            checkpoint_id=str(checkpoint.get("checkpoint_id") or ""),
            completed_coverage=list(checkpoint.get("completed_coverage") or []),
        )
        return PreemptionResult(True, metadata={"syscall_id": node.syscall_id, "checkpoint": checkpoint})


def _is_emergency_reason(reason: str) -> bool:
    normalized = reason.lower().replace("-", "_").replace(" ", "_")
    return any(marker in normalized for marker in ("emergency", "safety_interrupt", "collision", "estop", "e_stop"))


def _preemption_metadata(node: TaskNode, **metadata: Any) -> dict[str, Any]:
    payload = {
        "agent_id": node.agent_id,
        "app_id": node.app_id,
        "session_id": node.session_id,
        "task_graph_id": node.task_graph_id,
        "node_id": node.node_id,
        "syscall_id": node.syscall_id,
        "goal_id": node.user_goal_id,
        "capability": node.capability,
        "preempt_policy": node.preempt_policy,
    }
    payload.update(metadata)
    return payload


def _call_checkpoint_request(checkpoint_request, node: TaskNode, *, reason: str):
    try:
        return checkpoint_request(
            node.syscall_id,
            reason=reason,
            node_id=node.node_id,
            task_graph_id=node.task_graph_id,
            agent_id=node.agent_id,
        )
    except TypeError:
        return checkpoint_request(node.syscall_id)


def _response_success(response: Any) -> bool:
    if hasattr(response, "success"):
        return bool(getattr(response, "success"))
    if isinstance(response, dict):
        return bool(response.get("success"))
    return False


def _response_error_code(response: Any) -> str:
    if hasattr(response, "error_code"):
        return str(getattr(response, "error_code") or "")
    if isinstance(response, dict):
        return str(response.get("error_code") or "")
    return ""


def _extract_checkpoint_payload(node: TaskNode, response: Any) -> dict[str, Any]:
    mapping = _response_mapping(response)
    combined: dict[str, Any] = {}
    for key in ("response_message", "data", "metadata"):
        value = mapping.get(key)
        if isinstance(value, dict):
            combined.update(value)
    combined.update({key: value for key, value in mapping.items() if key not in {"response_message", "data", "metadata"}})

    checkpoint = combined.get("checkpoint")
    nested_checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
    checkpoint_id = str(
        combined.get("checkpoint_id")
        or nested_checkpoint.get("checkpoint_id")
        or nested_checkpoint.get("id")
        or checkpoint
        or ""
    )
    partial_result = _first_present(
        [combined, nested_checkpoint],
        ("partial_result", "partial_results", "partial_response", "partial_text"),
    )
    completed_coverage = _first_present(
        [combined, nested_checkpoint],
        ("completed_coverage", "coverage_completed", "covered_requirements"),
    )
    coverage_payload = list(completed_coverage) if isinstance(completed_coverage, list) else []

    if not checkpoint_id and partial_result is None and not coverage_payload:
        return {}

    payload: dict[str, Any] = {
        "syscall_id": node.syscall_id,
        "source": "kernel_service.checkpoint_request",
    }
    if checkpoint_id:
        payload["checkpoint_id"] = checkpoint_id
    if partial_result is not None:
        payload["partial_result"] = partial_result
    if coverage_payload:
        payload["completed_coverage"] = coverage_payload
    if nested_checkpoint:
        payload["checkpoint"] = nested_checkpoint
    return payload


def _response_mapping(response: Any) -> dict[str, Any]:
    if hasattr(response, "to_dict") and callable(response.to_dict):
        return dict(response.to_dict())
    if hasattr(response, "as_mapping") and callable(response.as_mapping):
        return dict(response.as_mapping())
    if isinstance(response, dict):
        return dict(response)
    return {}


def _first_present(mappings: list[dict[str, Any]], keys: tuple[str, ...]) -> Any:
    for mapping in mappings:
        for key in keys:
            if key in mapping:
                return mapping[key]
    return None
