from __future__ import annotations

from typing import Any

from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall


class HumanInteractionManager:
    """Scheduler-facing human interaction adapter."""

    def __init__(
        self,
        human_adapter: Any | None = None,
        access_manager: AccessManager | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.human_adapter = human_adapter
        self.access_manager = access_manager
        self.event_sink = event_sink
        self._events: list[dict[str, Any]] = []

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        if self.human_adapter is None:
            result = {
                "success": False,
                "error_code": "HUMAN_BACKEND_UNAVAILABLE",
                "reason": "runtime human backend not configured",
            }
            self._record(syscall, result)
            self._audit_result(syscall, result)
            return self._kernel_response(result)
        if syscall.operation_type in {"human.status", "human_status"}:
            return self._kernel_response(self.status())
        if syscall.operation_type in {"human.cancel", "human_cancel"} and hasattr(self.human_adapter, "cancel"):
            result = self.human_adapter.cancel(
                str(syscall.params.get("session_id") or "kernel"),
                str(syscall.params.get("call_id") or ""),
            )
            self._record(syscall, result)
            self._audit_result(syscall, result)
            return self._kernel_response(result)
        access = self._check_ask_access(syscall)
        if not access.get("success", True):
            self._record(syscall, access)
            self._audit_result(syscall, access)
            return self._kernel_response(access)
        if hasattr(self.human_adapter, "address_request"):
            result = self._normalize_backend_result(self.human_adapter.address_request(syscall))
            self._record(syscall, result)
            self._audit_result(syscall, result)
            return self._kernel_response(result)
        if hasattr(self.human_adapter, "ask"):
            result = self._normalize_backend_result(self.human_adapter.ask(syscall))
            self._record(syscall, result)
            self._audit_result(syscall, result)
            return self._kernel_response(result)
        if callable(self.human_adapter):
            result = self._normalize_backend_result(self.human_adapter(syscall))
            self._record(syscall, result)
            self._audit_result(syscall, result)
            return self._kernel_response(result)
        result = {"success": False, "error_code": "HUMAN_BACKEND_UNAVAILABLE", "reason": "human adapter invalid"}
        self._record(syscall, result)
        self._audit_result(syscall, result)
        return self._kernel_response(result)

    def status(self) -> dict[str, Any]:
        if self.human_adapter is None:
            return {
                "success": False,
                "state": "unavailable",
                "error_code": "HUMAN_BACKEND_UNAVAILABLE",
                "reason": "runtime human backend not configured",
                "recent_events": list(self._events[-20:]),
            }
        if hasattr(self.human_adapter, "status"):
            status = self.human_adapter.status()
        else:
            status = {"success": True, "state": "ready", "backend": self.human_adapter.__class__.__name__}
        status["recent_events"] = list(self._events[-20:])
        return status

    def _record(self, syscall: KernelSyscall, result: dict[str, Any]) -> None:
        self._events.append(
            {
                "operation_type": syscall.operation_type,
                "success": bool(result.get("success", False)),
                "error_code": str(result.get("error_code", "")),
            }
        )
        self._events = self._events[-100:]

    def _check_ask_access(self, syscall: KernelSyscall) -> dict[str, Any]:
        if self.access_manager is None:
            return {
                "success": False,
                "error_code": "ACCESS_MANAGER_UNAVAILABLE",
                "reason": "human.ask requires a kernel access manager",
                "requires_intervention": False,
            }
        query = getattr(syscall, "query", None)
        metadata = dict(getattr(query, "metadata", {}) or {})
        permissions = tuple(metadata.get("permissions") or syscall.params.get("permissions") or ())
        if "human.ask" not in permissions:
            return {
                "success": False,
                "error_code": "ACCESS_DENIED",
                "reason": "human.ask requires explicit human.ask permission",
                "requires_intervention": False,
            }
        session_id = str(
            getattr(query, "session_id", "")
            or metadata.get("session_id", "")
            or syscall.params.get("session_id", "")
            or "kernel"
        )
        app_id = str(getattr(query, "app_id", "") or syscall.agent_name)
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(
                    agent_name=syscall.agent_name,
                    app_id=app_id,
                    session_id=session_id,
                    permissions=permissions,
                ),
                action="execute",
                resource=AccessResource("human", "human.ask", owner_agent=syscall.agent_name),
                irreversible=True,
                reason="human ask requires an operator response",
            )
        )
        if decision.allowed:
            return {"success": True}
        return {
            "success": False,
            "error_code": decision.error_code,
            "reason": decision.reason,
            "requires_intervention": decision.requires_intervention,
            "intervention_id": decision.intervention_id,
        }

    def _audit_result(self, syscall: KernelSyscall, result: dict[str, Any]) -> None:
        if self.event_sink is not None:
            action = "cancel" if syscall.operation_type in {"human.cancel", "human_cancel"} else "ask"
            self.event_sink.emit(
                "human.audit",
                action=action,
                agent_name=syscall.agent_name,
                session_id=str(syscall.params.get("session_id") or "kernel"),
                call_id=str(syscall.params.get("call_id") or syscall.params.get("correlation_id") or ""),
                success=bool(result.get("success", False)),
                error_code=str(result.get("error_code") or ""),
                backend=self.human_adapter.__class__.__name__ if self.human_adapter is not None else "",
            )

    def _normalize_backend_result(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "success": False,
                "answered": False,
                "error_code": "HUMAN_RESULT_INVALID",
                "reason": f"human backend returned {type(result).__name__}",
            }
        normalized = dict(result)
        if "success" not in normalized and "answered" in normalized:
            answered = bool(normalized.get("answered", False))
            normalized["success"] = answered
            if not answered and not normalized.get("error_code"):
                normalized["error_code"] = "HUMAN_UNANSWERED"
        return normalized

    def _kernel_response(self, result: dict[str, Any]) -> KernelResponse:
        if result.get("success", False):
            return KernelResponse.ok(result, data=result)
        return KernelResponse.error(str(result.get("error_code") or "HUMAN_BACKEND_UNAVAILABLE"), metadata=result)
