from __future__ import annotations

from typing import Any

from agentic_os.kernel.system_call import KernelSyscall


class HumanInteractionManager:
    """Scheduler-facing human interaction adapter."""

    def __init__(self, human_adapter: Any | None = None) -> None:
        self.human_adapter = human_adapter

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        if self.human_adapter is None:
            return {"success": False, "error_code": "HUMAN_MANAGER_NOT_WIRED"}
        if hasattr(self.human_adapter, "address_request"):
            return self.human_adapter.address_request(syscall)
        if hasattr(self.human_adapter, "ask"):
            return self.human_adapter.ask(syscall)
        if callable(self.human_adapter):
            return self.human_adapter(syscall)
        return {"success": False, "error_code": "HUMAN_ADAPTER_INVALID"}
