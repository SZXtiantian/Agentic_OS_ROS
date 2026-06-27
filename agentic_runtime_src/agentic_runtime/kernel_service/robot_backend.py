from __future__ import annotations

import asyncio
from typing import Any

from agentic_os.kernel.system_call import KernelSyscall
from agentic_runtime.types import AppManifest


class RuntimeRobotCapabilityBackend:
    """Runtime-provided safe backend for kernel robot capability syscalls."""

    def __init__(self, runtime_server) -> None:
        self.runtime_server = runtime_server

    def execute_capability(self, syscall: KernelSyscall) -> dict[str, Any]:
        query = getattr(syscall, "query", None)
        skill_name = self._skill_name(syscall)
        params = self._capability_args(dict(getattr(query, "params", {}) or syscall.params or {}))
        app_id = str(getattr(query, "app_id", "") or syscall.agent_name)
        session_id = str(getattr(query, "session_id", "") or getattr(query, "metadata", {}).get("session_id", "") or params.pop("session_id", "") or "kernel")
        permissions = tuple(getattr(query, "metadata", {}).get("permissions") or params.pop("permissions", ()))
        agent_id = str(getattr(syscall, "agent_id", "") or getattr(syscall, "aid", "") or getattr(query, "metadata", {}).get("agent_id", "") or "")
        app = AppManifest(
            name=app_id,
            version="kernel",
            description="kernel robot capability request",
            entrypoint="kernel:robot",
            permissions=list(permissions),
            required_capabilities=[],
        )
        try:
            result = self._run(self.runtime_server.executor.execute(app, skill_name, params, session_id, agent_id=agent_id))
        except TypeError as exc:
            if agent_id or "agent_id" not in str(exc):
                raise
            result = self._run(self.runtime_server.executor.execute(app, skill_name, params, session_id))
        payload = result.to_dict()
        return {
            "success": result.success,
            "skill_name": skill_name,
            "result": payload,
            "error_code": result.error_code,
            "reason": result.reason,
            "audit_id": result.audit_id,
        }

    def _skill_name(self, syscall: KernelSyscall) -> str:
        query = getattr(syscall, "query", None)
        return str(getattr(query, "skill_name", "") or syscall.params.get("skill_name") or syscall.operation_type)

    def _capability_args(self, params: dict[str, Any]) -> dict[str, Any]:
        wrapped = params.get("args")
        if isinstance(wrapped, dict):
            args = dict(wrapped)
            if "permissions" in params and "permissions" not in args:
                args["permissions"] = params["permissions"]
            if "session_id" in params and "session_id" not in args:
                args["session_id"] = params["session_id"]
            return args
        return params

    def _run(self, awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("RuntimeRobotCapabilityBackend cannot run inside an active event loop")
