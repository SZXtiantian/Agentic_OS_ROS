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
            return {"success": True, "tool": name, "result": handler(dict(args or {}))}
        except Exception as exc:
            return {"success": False, "error_code": "TOOL_FAILED", "tool": name, "reason": str(exc)}
