from __future__ import annotations

from typing import Any

from agentic_os.kernel.skill_library import RuntimeSkillBackend
from agentic_os.kernel.system_call import KernelSyscall


class RuntimeHumanBackend:
    """Human lane backend that delegates to the real runtime human.ask skill."""

    def __init__(self, runtime_server: Any | None) -> None:
        self.runtime_server = runtime_server
        self.skill_backend = RuntimeSkillBackend(runtime_server)

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        params = dict(syscall.params)
        query = getattr(syscall, "query", None)
        session_id = str(getattr(query, "session_id", "") or params.pop("session_id", "") or "kernel")
        permissions = tuple(getattr(query, "metadata", {}).get("permissions") or params.pop("permissions", ()))
        skill_name = str(getattr(query, "skill_name", "") or params.pop("skill_name", "") or "human.ask")
        call_id = str(getattr(query, "call_id", "") or params.get("call_id") or params.get("correlation_id") or "")
        if syscall.operation_type in {"human.status", "human_status"}:
            return self.status()
        if syscall.operation_type in {"human.cancel", "human_cancel"}:
            return self.cancel(session_id, call_id=call_id)
        args = dict(params.get("args") or params)
        call_id = call_id or str(args.get("call_id") or args.get("correlation_id") or "")
        if "timeout_s" not in args:
            args["timeout_s"] = 60
        return self.skill_backend.call(
            skill_name,
            args,
            app_id=str(getattr(query, "app_id", "") or syscall.agent_name),
            session_id=session_id,
            permissions=permissions,
            call_id=call_id,
        )

    def status(self) -> dict[str, Any]:
        status = self.skill_backend.status()
        if not isinstance(status, dict):
            status = {
                "success": False,
                "state": "unavailable",
                "error_code": "HUMAN_RESULT_INVALID",
                "reason": f"skill backend status returned {type(status).__name__}",
            }
        if status.get("success", False):
            status["backend"] = "runtime_human_skill"
        human_channel = getattr(self.runtime_server, "human_channel", None)
        if human_channel is not None and hasattr(human_channel, "status"):
            channel_status = self._channel_status(human_channel)
            status["human_channel"] = channel_status
            if not channel_status.get("success", False):
                status["success"] = False
                status["state"] = "unavailable"
                status["error_code"] = str(channel_status.get("error_code") or "HUMAN_BACKEND_STATUS_UNAVAILABLE")
                status["reason"] = str(channel_status.get("reason") or "human channel status unavailable")
        return status

    def cancel(self, session_id: str, call_id: str = "") -> dict[str, Any]:
        human_channel = getattr(self.runtime_server, "human_channel", None)
        if call_id and human_channel is not None and hasattr(human_channel, "cancel"):
            result = self._channel_cancel(human_channel, session_id, call_id)
            if result.get("success", False):
                return result
            if result.get("error_code") != "SYSCALL_NOT_FOUND":
                return result
        return self.skill_backend.cancel(session_id, call_id=call_id)

    def _channel_status(self, human_channel: Any) -> dict[str, Any]:
        try:
            result = human_channel.status()
        except Exception as exc:
            return {
                "success": False,
                "state": "unavailable",
                "error_code": "HUMAN_BACKEND_STATUS_UNAVAILABLE",
                "reason": str(exc),
            }
        if not isinstance(result, dict):
            return {
                "success": False,
                "state": "unavailable",
                "error_code": "HUMAN_RESULT_INVALID",
                "reason": f"human channel status returned {type(result).__name__}",
            }
        if "success" not in result or not isinstance(result.get("success"), bool):
            return {
                "success": False,
                "state": "unavailable",
                "error_code": "HUMAN_RESULT_INVALID",
                "reason": "human channel status missing boolean success field",
                "data": dict(result),
            }
        return dict(result)

    def _channel_cancel(self, human_channel: Any, session_id: str, call_id: str) -> dict[str, Any]:
        try:
            result = human_channel.cancel(call_id, session_id=session_id)
        except Exception as exc:
            return {
                "success": False,
                "error_code": "HUMAN_BACKEND_UNAVAILABLE",
                "reason": str(exc),
                "session_id": session_id,
                "call_id": call_id,
            }
        if not isinstance(result, dict):
            return {
                "success": False,
                "error_code": "HUMAN_RESULT_INVALID",
                "reason": f"human channel cancel returned {type(result).__name__}",
                "session_id": session_id,
                "call_id": call_id,
            }
        if "success" not in result or not isinstance(result.get("success"), bool):
            return {
                "success": False,
                "error_code": "HUMAN_RESULT_INVALID",
                "reason": "human channel cancel missing boolean success field",
                "session_id": session_id,
                "call_id": call_id,
                "data": dict(result),
            }
        return dict(result)
