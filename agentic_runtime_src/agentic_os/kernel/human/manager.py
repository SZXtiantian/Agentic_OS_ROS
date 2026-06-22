from __future__ import annotations

from typing import Any

from agentic_os.kernel.system_call import KernelResponse, KernelSyscall


class HumanInteractionManager:
    """Scheduler-facing human interaction adapter."""

    def __init__(self, human_adapter: Any | None = None) -> None:
        self.human_adapter = human_adapter
        self._events: list[dict[str, Any]] = []

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        if self.human_adapter is None:
            return KernelResponse.error(
                "HUMAN_BACKEND_UNAVAILABLE",
                metadata={"reason": "runtime human backend not configured"},
            )
        if syscall.operation_type in {"human.status", "human_status"}:
            return self._kernel_response(self.status())
        if syscall.operation_type in {"human.cancel", "human_cancel"} and hasattr(self.human_adapter, "cancel"):
            return self._kernel_response(self.human_adapter.cancel(str(syscall.params.get("session_id") or "kernel"), str(syscall.params.get("call_id") or "")))
        if hasattr(self.human_adapter, "address_request"):
            result = self.human_adapter.address_request(syscall)
            self._record(syscall, result)
            return self._kernel_response(result)
        if hasattr(self.human_adapter, "ask"):
            result = self.human_adapter.ask(syscall)
            self._record(syscall, result)
            return self._kernel_response(result)
        if callable(self.human_adapter):
            result = self.human_adapter(syscall)
            self._record(syscall, result)
            return self._kernel_response(result)
        return KernelResponse.error("HUMAN_BACKEND_UNAVAILABLE", metadata={"reason": "human adapter invalid"})

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

    def _kernel_response(self, result: dict[str, Any]) -> KernelResponse:
        if result.get("success", False):
            return KernelResponse.ok(result, data=result)
        return KernelResponse.error(str(result.get("error_code") or "HUMAN_BACKEND_UNAVAILABLE"), metadata=result)
