from __future__ import annotations

from typing import Any

from agentic_os.kernel.skill_library import RuntimeSkillBackend
from agentic_os.kernel.system_call import KernelSyscall


class RuntimeHumanBackend:
    """Human lane backend that delegates to the real runtime human.ask skill."""

    def __init__(self, runtime_server: Any | None) -> None:
        self.skill_backend = RuntimeSkillBackend(runtime_server)

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        params = dict(syscall.params)
        query = getattr(syscall, "query", None)
        session_id = str(getattr(query, "session_id", "") or params.pop("session_id", "") or "kernel")
        permissions = tuple(getattr(query, "metadata", {}).get("permissions") or params.pop("permissions", ()))
        skill_name = str(getattr(query, "skill_name", "") or params.pop("skill_name", "") or "human.ask")
        if syscall.operation_type in {"human.status", "human_status"}:
            return self.status()
        if syscall.operation_type in {"human.cancel", "human_cancel"}:
            return self.cancel(session_id, call_id=str(params.get("call_id") or ""))
        args = dict(params.get("args") or params)
        if "timeout_s" not in args:
            args["timeout_s"] = 60
        return self.skill_backend.call(
            skill_name,
            args,
            app_id=str(getattr(query, "app_id", "") or syscall.agent_name),
            session_id=session_id,
            permissions=permissions,
        )

    def status(self) -> dict[str, Any]:
        status = self.skill_backend.status()
        if status.get("success", False):
            status["backend"] = "runtime_human_skill"
        return status

    def cancel(self, session_id: str, call_id: str = "") -> dict[str, Any]:
        return self.skill_backend.cancel(session_id, call_id=call_id)
