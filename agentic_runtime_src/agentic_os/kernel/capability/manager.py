from __future__ import annotations

from typing import Any, Protocol

from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelSyscall


class RobotCapabilityBackend(Protocol):
    def execute_capability(self, syscall: KernelSyscall) -> dict[str, Any]:
        ...


class RobotCapabilityManager:
    """Scheduler-facing robot capability adapter.

    This manager never imports ROS2 and never talks to robot hardware directly.
    A runtime-provided skill adapter must preserve the Permission -> Access ->
    Resource -> Safety -> Audit -> Bridge chain.
    """

    def __init__(
        self,
        backend: RobotCapabilityBackend | Any | None = None,
        skill_adapter: Any | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.skill_adapter = backend if backend is not None else skill_adapter
        self.event_sink = event_sink

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        if self.skill_adapter is None:
            if getattr(getattr(syscall, "query", None), "__class__", None).__name__ == "SkillQuery":
                result = {
                    "success": False,
                    "error_code": "SKILL_BACKEND_UNAVAILABLE",
                    "skill_name": self._skill_name(syscall),
                    "reason": "runtime robot skill backend not configured",
                }
                self._audit_result(syscall, result)
                return result
            result = {
                "success": False,
                "error_code": "ROBOT_MANAGER_NOT_WIRED",
                "skill_name": self._skill_name(syscall),
            }
            self._audit_result(syscall, result)
            return result
        if hasattr(self.skill_adapter, "execute_capability"):
            result = self._normalize_result(self.skill_adapter.execute_capability(syscall), syscall)
            self._audit_result(syscall, result)
            return result
        if hasattr(self.skill_adapter, "address_request"):
            result = self._normalize_result(self.skill_adapter.address_request(syscall), syscall)
            self._audit_result(syscall, result)
            return result
        if hasattr(self.skill_adapter, "execute_syscall"):
            result = self._normalize_result(self.skill_adapter.execute_syscall(syscall), syscall)
            self._audit_result(syscall, result)
            return result
        if callable(self.skill_adapter):
            result = self._normalize_result(self.skill_adapter(syscall), syscall)
            self._audit_result(syscall, result)
            return result
        result = {
            "success": False,
            "error_code": "ROBOT_SKILL_ADAPTER_INVALID",
            "skill_name": self._skill_name(syscall),
        }
        self._audit_result(syscall, result)
        return result

    def _skill_name(self, syscall: KernelSyscall) -> str:
        query = getattr(syscall, "query", None)
        return str(getattr(query, "skill_name", "") or syscall.params.get("skill_name") or syscall.operation_type)

    def _normalize_result(self, result: Any, syscall: KernelSyscall) -> dict[str, Any]:
        skill_name = self._skill_name(syscall)
        if not isinstance(result, dict):
            return {
                "success": False,
                "error_code": "ROBOT_RESULT_INVALID",
                "skill_name": skill_name,
                "reason": f"robot backend returned {type(result).__name__}",
            }
        if "success" not in result:
            return {
                "success": False,
                "error_code": "ROBOT_RESULT_INVALID",
                "skill_name": skill_name,
                "reason": "robot backend response missing success field",
                "data": dict(result),
            }
        if not isinstance(result.get("success"), bool):
            return {
                "success": False,
                "error_code": "ROBOT_RESULT_INVALID",
                "skill_name": skill_name,
                "reason": "robot backend response success field must be boolean",
                "data": dict(result),
            }
        if not result["success"] and not result.get("error_code"):
            normalized = dict(result)
            normalized["error_code"] = "ROBOT_BACKEND_FAILED"
            normalized.setdefault("reason", "robot backend failed without error_code")
            return normalized
        return result

    def _audit_result(self, syscall: KernelSyscall, result: dict[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(
                "robot.audit",
                operation_type=syscall.operation_type,
                skill_name=self._skill_name(syscall),
                agent_name=syscall.agent_name,
                success=bool(result.get("success", False)),
                error_code=str(result.get("error_code") or ""),
                backend=self.skill_adapter.__class__.__name__ if self.skill_adapter is not None else "",
            )
