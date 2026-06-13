from __future__ import annotations

from threading import Lock
from typing import Any, Callable

from agentic_os.kernel.system_call import KernelSyscall

ToolHandler = Callable[[dict[str, Any]], Any]


class ToolManager:
    """Conflict-aware generic tool manager ported from AIOS.

    Robot movement is explicitly excluded here. Robot capabilities must go
    through skill/system-call safety, device arbitration, and bridge layers.
    """

    def __init__(self) -> None:
        self._registry: dict[str, ToolHandler] = {}
        self._active: set[str] = set()
        self._lock = Lock()

    def register(self, name: str, handler: ToolHandler) -> None:
        self._registry[name] = handler

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        tool_name = str(syscall.params.get("name") or syscall.operation_type)
        tool_args = dict(syscall.params.get("args") or syscall.params.get("parameters") or {})
        if tool_name.startswith("robot."):
            return {"success": False, "error_code": "TOOL_FORBIDDEN_ROBOT_CAPABILITY"}
        handler = self._registry.get(tool_name)
        if handler is None:
            return {"success": False, "error_code": "TOOL_NOT_FOUND", "tool": tool_name}
        with self._lock:
            if tool_name in self._active:
                return {"success": False, "error_code": "TOOL_BUSY", "tool": tool_name}
            self._active.add(tool_name)
        try:
            return {"success": True, "tool": tool_name, "result": handler(tool_args)}
        except Exception as exc:
            return {"success": False, "error_code": "TOOL_FAILED", "reason": str(exc), "tool": tool_name}
        finally:
            with self._lock:
                self._active.discard(tool_name)

