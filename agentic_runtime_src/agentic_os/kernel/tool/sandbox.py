from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolSandboxPolicy:
    allow_network: bool = False
    allowed_modes: tuple[str, ...] = ("in_process",)
    allowed_filesystems: tuple[str, ...] = ("read_only", "workspace_write", "none")
    workspace_root: Path | None = None
    default_mode: str = "in_process"
    default_filesystem: str = "read_only"
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalize(self, sandbox: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = dict(sandbox or {})
        filesystem = raw.get("filesystem", self.default_filesystem)
        if filesystem is False:
            filesystem = "none"
        elif filesystem is True:
            filesystem = "workspace_write"
        normalized = {
            "mode": str(raw.get("mode") or self.default_mode),
            "network": bool(raw.get("network", False)),
            "filesystem": str(filesystem),
        }
        if "workspace" in raw:
            normalized["workspace"] = str(raw["workspace"])
        return normalized

    def validate(self, sandbox: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = self.normalize(sandbox)
        if normalized["mode"] not in self.allowed_modes:
            return {
                "success": False,
                "error_code": "TOOL_SANDBOX_MODE_DISABLED",
                "reason": f"sandbox mode disabled: {normalized['mode']}",
                "sandbox": normalized,
            }
        if normalized["network"] and not self.allow_network:
            return {
                "success": False,
                "error_code": "TOOL_SANDBOX_NETWORK_DISABLED",
                "reason": "tool sandbox network access is disabled",
                "sandbox": normalized,
            }
        if normalized["filesystem"] not in self.allowed_filesystems:
            return {
                "success": False,
                "error_code": "TOOL_SANDBOX_FILESYSTEM_DENIED",
                "reason": f"tool sandbox filesystem mode denied: {normalized['filesystem']}",
                "sandbox": normalized,
            }
        workspace = normalized.get("workspace")
        if workspace and self.workspace_root is not None:
            root = self.workspace_root.resolve()
            path = (root / str(workspace)).resolve()
            if root not in path.parents and path != root:
                return {
                    "success": False,
                    "error_code": "TOOL_SANDBOX_WORKSPACE_DENIED",
                    "reason": "tool sandbox workspace escapes tool root",
                    "sandbox": normalized,
                }
        return {"success": True, "sandbox": normalized}

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_network": self.allow_network,
            "allowed_modes": list(self.allowed_modes),
            "allowed_filesystems": list(self.allowed_filesystems),
            "workspace_root": str(self.workspace_root) if self.workspace_root else "",
            "default_mode": self.default_mode,
            "default_filesystem": self.default_filesystem,
        }
