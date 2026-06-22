from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Callable

from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall

from .builtins import builtin_tools
from .loader import ToolLoader
from .manifest import ToolManifest
from .mcp_server import MCPToolServer
from .sandbox import ToolSandboxPolicy

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
        sandbox_policy: ToolSandboxPolicy | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.tool_root = Path(tool_root).resolve() if tool_root else None
        self.loader = ToolLoader(self.tool_root) if self.tool_root else None
        self.access_manager = access_manager
        self.mcp_server = mcp_server or MCPToolServer(enabled=False)
        self.sandbox_policy = sandbox_policy or ToolSandboxPolicy(workspace_root=self.tool_root)
        self.event_sink = event_sink
        self._registry: dict[str, ToolHandler] = {}
        self._conflicts: dict[str, set[str]] = {}
        self._descriptions: dict[str, str] = {}
        self._manifests: dict[str, ToolManifest] = {}
        self._active: set[str] = set()
        self._lock = Lock()
        self._audit_events: list[dict[str, Any]] = []
        self._register_builtin_tools()

    def register(
        self,
        name: str,
        handler: ToolHandler,
        conflicts: list[str] | tuple[str, ...] | None = None,
        *,
        description: str = "",
    ) -> None:
        if self._is_forbidden(name):
            raise ValueError("TOOL_FORBIDDEN_ROBOT_CAPABILITY")
        self._registry[name] = handler
        self._descriptions[name] = description
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
        access = self._check_access("installer", manifest.name, tuple(manifest.permissions), action="install")
        if not access.get("success", True):
            raise ValueError(str(access.get("error_code") or "TOOL_INSTALL_DENIED"))
        sandbox = self.sandbox_policy.validate(manifest.sandbox)
        if not sandbox.get("success", False):
            raise ValueError(str(sandbox.get("error_code") or "TOOL_SANDBOX_DENIED"))
        handler = self.loader.load(manifest)
        self.register(manifest.name, handler, conflicts=manifest.conflicts or (manifest.name,), description=manifest.description)
        self._manifests[manifest.name] = manifest
        return manifest

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        operation = syscall.operation_type
        params = syscall.params
        try:
            if operation in {"tool_call", "call_tool", "call"}:
                return self._kernel_response(
                    self.call_tool(
                        syscall.agent_name,
                        str(params.get("name") or operation),
                        dict(params.get("args") or params.get("parameters") or {}),
                        tuple(params.get("permissions") or ()),
                    )
                )
            if operation == "tool_list":
                return self._kernel_response({"success": True, "tools": self.list_tools()})
            if operation == "tool_describe":
                return self._kernel_response(self.describe(str(params.get("name") or params.get("tool") or "")))
            if operation == "tool_load_manifest":
                access = self._check_access(syscall.agent_name, str(params.get("path") or ""), (), action="install", irreversible=True)
                if not access.get("success", True):
                    return self._kernel_response(access)
                manifest = self.load_manifest(str(params.get("path") or ""))
                return self._kernel_response({"success": True, "tool": manifest.name, "manifest": manifest.__dict__})
            if operation == "tool_unload":
                return self._kernel_response(self.unload(syscall.agent_name, str(params.get("name") or "")))
            if operation == "tool_register_builtin":
                return self._kernel_response(self.register_builtin(syscall.agent_name, str(params.get("name") or "")))
            if operation == "tool_status":
                return self._kernel_response({"success": True, "status": self.status()})
            if operation == "tool_cancel":
                return self._kernel_response({"success": False, "error_code": "TOOL_CANCEL_UNSUPPORTED"})
            return self._kernel_response(
                self.call_tool(
                    syscall.agent_name,
                    str(params.get("name") or operation),
                    dict(params.get("args") or params.get("parameters") or {}),
                    tuple(params.get("permissions") or ()),
                )
            )
        except ValueError as exc:
            return KernelResponse.error(str(exc) or "TOOL_MANIFEST_INVALID")
        except Exception as exc:
            return KernelResponse.error("TOOL_BACKEND_UNAVAILABLE", metadata={"reason": str(exc)})

    def call_tool(
        self,
        agent_name: str,
        tool_name: str,
        tool_args: dict[str, Any],
        permissions: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if self._is_forbidden(tool_name):
            return {"success": False, "error_code": "TOOL_FORBIDDEN_ROBOT_CAPABILITY"}
        access = self._check_access(agent_name, tool_name, permissions)
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
            self._record_tool_event("tool.started", agent_name, tool_name)
            return {"success": True, "tool": tool_name, "result": handler(tool_args)}
        except Exception as exc:
            self._record_tool_event("tool.failed", agent_name, tool_name, {"reason": str(exc)})
            return {"success": False, "error_code": "TOOL_FAILED", "reason": str(exc), "tool": tool_name}
        finally:
            self._record_tool_event("tool.done", agent_name, tool_name)
            with self._lock:
                self._active.difference_update(conflicts)

    def list_tools(self) -> list[dict[str, Any]]:
        return [self.describe(name) for name in sorted(self._registry)]

    def describe(self, name: str) -> dict[str, Any]:
        if name not in self._registry:
            return {"success": False, "error_code": "TOOL_NOT_FOUND", "tool": name}
        manifest = self._manifests.get(name)
        return {
            "success": True,
            "tool": name,
            "description": self._descriptions.get(name, ""),
            "conflicts": sorted(self._conflicts.get(name, {name})),
            "manifest": manifest.__dict__ if manifest is not None else None,
            "builtin": manifest is None,
        }

    def unload(self, agent_name: str, name: str) -> dict[str, Any]:
        access = self._check_access(agent_name, name, (), action="uninstall", irreversible=True)
        if not access.get("success", True):
            return access
        if name not in self._registry:
            return {"success": False, "error_code": "TOOL_NOT_FOUND", "tool": name}
        if name in builtin_tools(self.tool_root or Path.cwd()):
            return {"success": False, "error_code": "TOOL_BUILTIN_UNLOAD_DENIED", "tool": name}
        self._registry.pop(name, None)
        self._conflicts.pop(name, None)
        self._descriptions.pop(name, None)
        self._manifests.pop(name, None)
        return {"success": True, "tool": name}

    def register_builtin(self, agent_name: str, name: str) -> dict[str, Any]:
        access = self._check_access(agent_name, name, (), action="install", irreversible=True)
        if not access.get("success", True):
            return access
        builtins = builtin_tools(self.tool_root or Path.cwd())
        if name not in builtins:
            return {"success": False, "error_code": "TOOL_NOT_FOUND", "tool": name}
        handler, description = builtins[name]
        self.register(name, handler, description=description)
        return {"success": True, "tool": name}

    def _is_forbidden(self, name: str, permissions: tuple[str, ...] = ()) -> bool:
        lowered = name.lower()
        values = [lowered, *(permission.lower() for permission in permissions)]
        return any(any(value.startswith(prefix) or prefix in value for prefix in _forbidden_prefixes()) for value in values)

    def _check_access(
        self,
        agent_name: str,
        tool_name: str,
        permissions: tuple[str, ...],
        *,
        action: str = "execute",
        irreversible: bool = False,
    ) -> dict[str, Any]:
        if self.access_manager is None:
            return {"success": True}
        groups = ("admin",) if action in {"install", "uninstall"} else ()
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(agent_name=agent_name, groups=groups, permissions=permissions),
                action=action,
                resource=AccessResource("tool", tool_name),
                irreversible=irreversible,
            )
        )
        if decision.allowed:
            return {"success": True}
        return {
            "success": False,
            "error_code": decision.error_code,
            "reason": decision.reason,
            "requires_intervention": decision.requires_intervention,
        }

    def status(self) -> dict[str, Any]:
        return {
            "tool_count": len(self._registry),
            "active": sorted(self._active),
            "registered": sorted(self._registry),
            "mcp": self.mcp_server.status(),
            "sandbox": self.sandbox_policy.to_dict(),
            "recent_events": list(self._audit_events[-20:]),
        }

    def _register_builtin_tools(self) -> None:
        for name, (handler, description) in builtin_tools(self.tool_root or Path.cwd()).items():
            self.register(name, handler, description=description)

    def _kernel_response(self, result: dict[str, Any]) -> KernelResponse:
        if result.get("success", False):
            return KernelResponse.ok(result, data=result)
        return KernelResponse.error(str(result.get("error_code") or "TOOL_BACKEND_UNAVAILABLE"), metadata=result)

    def _record_tool_event(
        self,
        event_type: str,
        agent_name: str,
        tool_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._audit_events.append(
            {
                "event_type": event_type,
                "agent_name": agent_name,
                "tool": tool_name,
                "metadata": dict(metadata or {}),
            }
        )
        if self.event_sink is not None:
            self.event_sink.emit(event_type, agent_name=agent_name, tool=tool_name, metadata=dict(metadata or {}))
