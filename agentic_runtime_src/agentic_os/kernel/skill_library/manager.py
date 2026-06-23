from __future__ import annotations

from typing import Any

from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall

from .backend import RuntimeSkillBackend


class SkillManager:
    def __init__(self, backend: RuntimeSkillBackend | Any | None = None, event_sink: KernelEventSink | None = None) -> None:
        self.backend = backend
        self.event_sink = event_sink
        self._events: list[dict[str, Any]] = []

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        operation = syscall.operation_type
        params = dict(syscall.params)
        query = getattr(syscall, "query", None)
        skill_name = str(getattr(query, "skill_name", "") or params.get("skill_name") or params.get("name") or operation)
        session_id = str(getattr(query, "session_id", "") or params.pop("session_id", "") or "kernel")
        call_id = str(getattr(query, "call_id", "") or params.get("call_id") or "")
        permissions = tuple(getattr(query, "metadata", {}).get("permissions") or params.pop("permissions", ()) or ())
        try:
            if operation in {"skill_call", "call_skill", "execute_skill"} or "." in operation:
                response = self.call(
                    skill_name,
                    dict(params.get("args") or params.get("parameters") or params),
                    app_id=str(getattr(query, "app_id", "") or syscall.agent_name),
                    session_id=session_id,
                    permissions=permissions,
                    call_id=call_id,
                )
            elif operation == "skill_list":
                response = self.list()
            elif operation == "skill_describe":
                response = self.describe(skill_name)
            elif operation == "skill_status":
                response = self.status(call_id=str(params.get("call_id") or getattr(query, "call_id", "")))
            elif operation == "skill_cancel":
                response = self.cancel(session_id, call_id=call_id)
            else:
                response = {"success": False, "error_code": "SKILL_OPERATION_UNSUPPORTED", "operation": operation}
        except Exception as exc:
            response = {"success": False, "error_code": "SKILL_BACKEND_UNAVAILABLE", "reason": str(exc)}
        response = self._normalize_response(response, operation, skill_name)
        self._record(operation, skill_name, response)
        self._audit_result(operation, skill_name, session_id, response)
        return self._kernel_response(response)

    def call(
        self,
        skill_name: str,
        args: dict[str, Any],
        *,
        app_id: str,
        session_id: str,
        permissions: tuple[str, ...] = (),
        call_id: str = "",
    ) -> dict[str, Any]:
        if self.backend is None:
            return self._unavailable(skill_name, "runtime skill backend not configured")
        return self.backend.call(skill_name, args, app_id=app_id, session_id=session_id, permissions=permissions, call_id=call_id)

    def list(self) -> dict[str, Any]:
        if self.backend is None:
            return self._unavailable("", "runtime skill backend not configured")
        return self.backend.list()

    def describe(self, skill_name: str) -> dict[str, Any]:
        if self.backend is None:
            return self._unavailable(skill_name, "runtime skill backend not configured")
        return self.backend.describe(skill_name)

    def status(self, call_id: str = "") -> dict[str, Any]:
        if self.backend is None:
            return self._unavailable("", "runtime skill backend not configured")
        status = self.backend.status()
        if status.get("success", False):
            active_calls = list(status.get("active_calls") or [])
            if call_id and not any(str(call.get("call_id") or "") == call_id for call in active_calls if isinstance(call, dict)):
                return {
                    "success": False,
                    "error_code": "SYSCALL_NOT_FOUND",
                    "reason": "skill call_id is not active",
                    "call_id": call_id,
                    "active_calls": active_calls,
                }
            status["call_id"] = call_id
            status["recent_events"] = list(self._events[-20:])
        return status

    def cancel(self, session_id: str, call_id: str = "") -> dict[str, Any]:
        if self.backend is None:
            return self._unavailable("", "runtime skill backend not configured")
        if not call_id:
            return {"success": False, "error_code": "SYSCALL_NOT_FOUND", "reason": "call_id required", "session_id": session_id}
        return self.backend.cancel(session_id, call_id=call_id)

    def _unavailable(self, skill_name: str, reason: str) -> dict[str, Any]:
        return {
            "success": False,
            "error_code": "SKILL_BACKEND_UNAVAILABLE",
            "skill_name": skill_name,
            "reason": reason,
        }

    def _record(self, operation: str, skill_name: str, response: dict[str, Any]) -> None:
        self._events.append(
            {
                "operation_type": operation,
                "skill_name": skill_name,
                "success": bool(response.get("success", False)),
                "error_code": str(response.get("error_code", "")),
            }
        )
        self._events = self._events[-100:]

    def _normalize_response(self, response: Any, operation: str, skill_name: str) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {
                "success": False,
                "error_code": "SKILL_RESULT_INVALID",
                "reason": "skill backend response must be an object",
                "operation": operation,
                "skill_name": skill_name,
                "raw_type": type(response).__name__,
            }
        if "success" not in response:
            return {
                "success": False,
                "error_code": "SKILL_RESULT_INVALID",
                "reason": "skill backend response missing success field",
                "operation": operation,
                "skill_name": skill_name,
                "data": dict(response),
            }
        return response

    def _audit_result(self, operation: str, skill_name: str, session_id: str, response: dict[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(
                "skill.audit",
                operation_type=operation,
                skill_name=skill_name,
                session_id=session_id,
                success=bool(response.get("success", False)),
                error_code=str(response.get("error_code") or ""),
                backend=self.backend.__class__.__name__ if self.backend is not None else "",
            )

    def _kernel_response(self, result: dict[str, Any]) -> KernelResponse:
        if result.get("success", False):
            return KernelResponse.ok(result, data=result)
        return KernelResponse.error(str(result.get("error_code") or "SKILL_BACKEND_UNAVAILABLE"), metadata=result)
