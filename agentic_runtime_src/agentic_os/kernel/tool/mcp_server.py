from __future__ import annotations

import os


class MCPToolServer:
    def __init__(self, enabled: bool | None = None) -> None:
        self.enabled = bool(os.environ.get("AGENTIC_ENABLE_MCP_TOOLS") == "1") if enabled is None else enabled

    def status(self) -> dict[str, object]:
        return {"enabled": self.enabled, "implemented": False}
