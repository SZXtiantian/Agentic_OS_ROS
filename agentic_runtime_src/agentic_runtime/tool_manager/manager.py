from __future__ import annotations

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelSyscall
from agentic_os.kernel.tool import ToolManager as KernelToolManager

from agentic_runtime.audit import AuditLogger

from .models import ToolCall, ToolResult
from .registry import ToolRegistry


class ToolManager:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        audit_logger: AuditLogger | None = None,
        *,
        access_manager: AccessManager | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry.default()
        self.audit_logger = audit_logger
        self.kernel = KernelToolManager(access_manager=access_manager, event_sink=event_sink)
        for name in self.registry.list_tools():
            handler = self.registry.get(name)
            if handler is not None:
                self.kernel.register(name, handler)

    def call(self, call: ToolCall) -> ToolResult:
        syscall = KernelSyscall.create(
            call.app_id or "runtime",
            "tool",
            call.name,
            {"name": call.name, "args": call.args, "permissions": tuple(call.permissions)},
        )
        raw = self.kernel.address_request(syscall)
        raw_success = raw.get("success")
        if raw_success is True:
            data = raw.get("result")
            return self._finish(call, ToolResult(True, data=data if isinstance(data, dict) else {"result": data}))
        if not isinstance(raw_success, bool):
            return self._finish(
                call,
                ToolResult(
                    False,
                    error_code="TOOL_RESULT_INVALID",
                    reason="kernel tool result success field must be boolean",
                ),
            )
        error_code = str(raw.get("error_code") or "TOOL_FAILED")
        if error_code == "TOOL_FORBIDDEN_ROBOT_CAPABILITY":
            error_code = "TOOL_FORBIDDEN"
        return self._finish(
            call,
            ToolResult(
                False,
                error_code=error_code,
                reason=str(raw.get("reason") or raw.get("tool") or f"unknown tool: {call.name}"),
            ),
        )

    def _finish(self, call: ToolCall, result: ToolResult) -> ToolResult:
        if self.audit_logger is not None:
            result.audit_id = self.audit_logger.write(
                {
                    "app_id": call.app_id,
                    "session_id": call.session_id,
                    "skill_name": f"tool.{call.name}",
                    "args": call.args,
                    "permission_result": "allowed" if result.success else "denied",
                    "safety_result": "not_required",
                    "resource_lock_result": "not_required",
                    "backend": "tool_manager",
                    "status": "succeeded" if result.success else "rejected",
                    "error_code": result.error_code,
                    "duration_ms": 0,
                }
            )
        return result
