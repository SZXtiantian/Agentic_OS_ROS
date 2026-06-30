from __future__ import annotations

import asyncio
import inspect
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
        result = self._run(
            self._execute_runtime_skill(
                app,
                skill_name,
                params,
                session_id,
                agent_id=agent_id,
                call_id=str(getattr(syscall, "syscall_id", "") or ""),
            )
        )
        payload = result.to_dict()
        return {
            "success": result.success,
            "skill_name": skill_name,
            "result": payload,
            "error_code": result.error_code,
            "reason": result.reason,
            "audit_id": result.audit_id,
        }

    def checkpoint_request(self, syscall: KernelSyscall, **metadata: Any) -> dict[str, Any]:
        executor = getattr(self.runtime_server, "executor", None)
        if executor is None:
            return self._checkpoint_unavailable("runtime executor not configured", syscall)
        checkpoint_method = getattr(executor, "checkpoint_capability", None) or getattr(executor, "checkpoint_request", None)
        if not callable(checkpoint_method):
            return self._checkpoint_unavailable("runtime executor does not expose checkpoint capability", syscall)
        try:
            result = checkpoint_method(syscall, **metadata)
        except TypeError:
            try:
                result = checkpoint_method(syscall.syscall_id)
            except TypeError:
                result = checkpoint_method(syscall)
        if hasattr(result, "__await__"):
            result = self._run(result)
        return self._checkpoint_result(result, syscall)

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

    def _execute_runtime_skill(
        self,
        app: AppManifest,
        skill_name: str,
        params: dict[str, Any],
        session_id: str,
        *,
        agent_id: str = "",
        call_id: str = "",
    ):
        execute = self.runtime_server.executor.execute
        kwargs: dict[str, Any] = {}
        try:
            signature = inspect.signature(execute)
        except (TypeError, ValueError):
            signature = None
        if signature is not None:
            parameters = signature.parameters
            accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values())
            if call_id and ("call_id" in parameters or accepts_kwargs):
                kwargs["call_id"] = call_id
            if agent_id and ("agent_id" in parameters or accepts_kwargs):
                kwargs["agent_id"] = agent_id
        else:
            if call_id:
                kwargs["call_id"] = call_id
            if agent_id:
                kwargs["agent_id"] = agent_id
        return execute(app, skill_name, params, session_id, **kwargs)

    def _checkpoint_result(self, result: Any, syscall: KernelSyscall) -> dict[str, Any]:
        skill_name = self._skill_name(syscall)
        if hasattr(result, "to_dict") and callable(result.to_dict):
            payload = result.to_dict()
            data = dict(payload.get("data") or {}) if isinstance(payload, dict) else {}
            return {
                "success": bool(payload.get("success", False)),
                "skill_name": skill_name,
                **data,
                "result": payload,
                "error_code": str(payload.get("error_code") or ""),
                "reason": str(payload.get("reason") or ""),
                "audit_id": str(payload.get("audit_id") or ""),
            }
        if isinstance(result, dict):
            payload = dict(result)
            payload.setdefault("skill_name", skill_name)
            return payload
        return {
            "success": False,
            "error_code": "ROBOT_RESULT_INVALID",
            "skill_name": skill_name,
            "reason": f"robot checkpoint backend returned {type(result).__name__}",
        }

    def _checkpoint_unavailable(self, reason: str, syscall: KernelSyscall) -> dict[str, Any]:
        return {
            "success": False,
            "error_code": "SCHEDULER_PREEMPTION_UNSUPPORTED",
            "skill_name": self._skill_name(syscall),
            "reason": reason,
            "syscall_id": syscall.syscall_id,
        }
