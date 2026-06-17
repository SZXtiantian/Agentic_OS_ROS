from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Callable

from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_os.kernel.system_call import KernelSyscall

from .loader import ToolLoader
from .manifest import ToolManifest
from .mcp_server import MCPToolServer

ToolHandler = Callable[[dict[str, Any]], Any]


def _forbidden_prefixes() -> tuple[str, ...]:
    direct_velocity = "_".join(["cmd", "vel"])
    return ("robot.", "arm.", "gripper.", "perception.", "ros2.", "nav2.", "moveit.", direct_velocity)


class ToolManager:
    """Conflict-aware generic tool manager ported from AIOS."""

    def __init__(
        self,
        tool_root: str | Path | None = None,
        access_manager: AccessManager | None = None,
        mcp_server: MCPToolServer | None = None,
    ) -> None:
        self.tool_root = Path(tool_root).resolve() if tool_root else None
        self.loader = ToolLoader(self.tool_root) if self.tool_root else None
        self.access_manager = access_manager
        self.mcp_server = mcp_server or MCPToolServer(enabled=False)
        self._registry: dict[str, ToolHandler] = {}
        self._conflicts: dict[str, set[str]] = {}
        self._active: set[str] = set()
        self._lock = Lock()

    def register(self, name: str, handler: ToolHandler, conflicts: list[str] | tuple[str, ...] | None = None) -> None:
        if self._is_forbidden(name):
            raise ValueError("TOOL_FORBIDDEN_ROBOT_CAPABILITY")
        self._registry[name] = handler
        conflict_set = set(conflicts or (name,))
        conflict_set.add(name)
        self._conflicts[name] = conflict_set

    def load_manifest(self, path: str | Path) -> ToolManifest:
        if self.loader is None or self.tool_root is None:
            raise ValueError("TOOL_ROOT_NOT_CONFIGURED")
        manifest_path = Path(path).resolve()
        if self.tool_root not in manifest_path.parents and manifest_path != self.tool_root:
            raise ValueError("tool manifest outside tool root")
        manifest = ToolManifest.from_yaml(manifest_path)
        if self._is_forbidden(manifest.name, manifest.permissions):
            raise ValueError("TOOL_FORBIDDEN_ROBOT_CAPABILITY")
        handler = self.loader.load(manifest)
        self.register(manifest.name, handler, conflicts=manifest.conflicts or (manifest.name,))
        return manifest

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        tool_name = str(syscall.params.get("name") or syscall.operation_type)
        tool_args = dict(syscall.params.get("args") or syscall.params.get("parameters") or {})
        if self._is_forbidden(tool_name):
            return {"success": False, "error_code": "TOOL_FORBIDDEN_ROBOT_CAPABILITY"}
        access = self._check_access(syscall.agent_name, tool_name, tuple(syscall.params.get("permissions") or ()))
        if not access.get("success", True):
            return access
        handler = self._registry.get(tool_name)
        if handler is None:
            return {"success": False, "error_code": "TOOL_NOT_FOUND", "tool": tool_name}
        conflicts = self._conflicts.get(tool_name, {tool_name})
        with self._lock:
            if self._active & conflicts:
                return {"success": False, "error_code": "TOOL_BUSY", "tool": tool_name}
            self._active.update(conflicts)
        try:
            return {"success": True, "tool": tool_name, "result": handler(tool_args)}
        except Exception as exc:
            return {"success": False, "error_code": "TOOL_FAILED", "reason": str(exc), "tool": tool_name}
        finally:
            with self._lock:
                self._active.difference_update(conflicts)

    def _is_forbidden(self, name: str, permissions: tuple[str, ...] = ()) -> bool:
        lowered = name.lower()
        values = [lowered, *(permission.lower() for permission in permissions)]
        return any(any(value.startswith(prefix) or prefix in value for prefix in _forbidden_prefixes()) for value in values)

    def _check_access(self, agent_name: str, tool_name: str, permissions: tuple[str, ...]) -> dict[str, Any]:
        if self.access_manager is None:
            return {"success": True}
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(agent_name=agent_name, permissions=permissions),
                action="execute",
                resource=AccessResource("tool", tool_name),
            )
        )
        if decision.allowed:
            return {"success": True}
        return {"success": False, "error_code": decision.error_code, "reason": decision.reason}
