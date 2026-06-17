from __future__ import annotations

from typing import Any

from agentic_os.kernel.system_call import KernelSyscall


class RobotCapabilityManager:
    """Scheduler-facing robot capability adapter.

    This manager never imports ROS2 and never talks to robot hardware directly.
    A runtime-provided skill adapter must preserve the Permission -> Access ->
    Resource -> Safety -> Audit -> Bridge chain.
    """

    def __init__(self, skill_adapter: Any | None = None) -> None:
        self.skill_adapter = skill_adapter

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        if self.skill_adapter is None:
            return {
                "success": False,
                "error_code": "ROBOT_MANAGER_NOT_WIRED",
                "skill_name": self._skill_name(syscall),
            }
        if hasattr(self.skill_adapter, "address_request"):
            return self.skill_adapter.address_request(syscall)
        if hasattr(self.skill_adapter, "execute_syscall"):
            return self.skill_adapter.execute_syscall(syscall)
        if callable(self.skill_adapter):
            return self.skill_adapter(syscall)
        return {
            "success": False,
            "error_code": "ROBOT_SKILL_ADAPTER_INVALID",
            "skill_name": self._skill_name(syscall),
        }

    def _skill_name(self, syscall: KernelSyscall) -> str:
        query = getattr(syscall, "query", None)
        return str(getattr(query, "skill_name", "") or syscall.params.get("skill_name") or syscall.operation_type)
