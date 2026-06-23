from __future__ import annotations

import os
from typing import Any, Callable


MCPToolHandler = Callable[[dict[str, Any]], Any]


class MCPToolServer:
    def __init__(self, enabled: bool | None = None) -> None:
        self.enabled = bool(os.environ.get("AGENTIC_ENABLE_MCP_TOOLS") == "1") if enabled is None else enabled
        self._running = False
        self._tools: dict[str, MCPToolHandler] = {}

    def start(self) -> dict[str, object]:
        if not self.enabled:
            return {"success": False, "error_code": "TOOL_MCP_DISABLED"}
        self._running = True
        return {"success": True, "status": "running"}

    def stop(self) -> dict[str, object]:
        self._running = False
        return {"success": True, "status": "stopped"}

    def status(self) -> dict[str, object]:
        return {"enabled": self.enabled, "implemented": True, "running": self._running, "tool_count": len(self._tools)}

    def register_tool(self, name: str, handler: MCPToolHandler) -> None:
        self._tools[name] = handler

    def list_tools(self) -> dict[str, object]:
        if not self.enabled:
            return {"success": False, "error_code": "TOOL_MCP_DISABLED", "tools": []}
        if not self._running:
            return {"success": False, "error_code": "TOOL_MCP_NOT_RUNNING", "tools": []}
        return {"success": True, "tools": sorted(self._tools)}

    def call_tool(self, name: str, args: dict[str, Any] | None = None) -> dict[str, object]:
        if not self.enabled:
            return {"success": False, "error_code": "TOOL_MCP_DISABLED"}
        if not self._running:
            return {"success": False, "error_code": "TOOL_MCP_NOT_RUNNING"}
        handler = self._tools.get(name)
        if handler is None:
            return {"success": False, "error_code": "TOOL_NOT_FOUND", "tool": name}
        try:
            result = handler(dict(args or {}))
            normalized = self._normalize_handler_result(name, result)
            if not normalized.get("success", False):
                return normalized
            return {"success": True, "tool": name, "result": result}
        except Exception as exc:
            return {"success": False, "error_code": "TOOL_FAILED", "tool": name, "reason": str(exc)}

    def _normalize_handler_result(self, name: str, result: Any) -> dict[str, object]:
        if not isinstance(result, dict) or "success" not in result:
            return {"success": True, "tool": name, "result": result}
        if not isinstance(result.get("success"), bool):
            return {
                "success": False,
                "error_code": "TOOL_RESULT_INVALID",
                "reason": "tool handler result success field must be bool",
                "tool": name,
                "result": result,
            }
        if result.get("success"):
            return {"success": True, "tool": name, "result": result}
        return {
            "success": False,
            "error_code": str(result.get("error_code") or "TOOL_FAILED"),
            "reason": str(result.get("reason") or result.get("message") or "tool handler reported failure"),
            "tool": name,
            "result": result,
        }
