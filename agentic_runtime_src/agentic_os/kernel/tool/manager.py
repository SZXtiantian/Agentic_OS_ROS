from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Any, Callable
from uuid import uuid4

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


@dataclass
class _ActiveToolCall:
    call_id: str
    agent_name: str
    tool_name: str
    conflicts: set[str]
    cancel_event: Event


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
        self._active_calls: dict[str, _ActiveToolCall] = {}
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

    def load_manifest(
        self,
        path: str | Path,
        *,
        agent_name: str = "installer",
        permissions: tuple[str, ...] = (),
        check_access: bool = True,
    ) -> ToolManifest:
        if self.loader is None or self.tool_root is None:
            raise ValueError("TOOL_ROOT_NOT_CONFIGURED")
        manifest_path = Path(path).resolve()
        if self.tool_root not in manifest_path.parents and manifest_path != self.tool_root:
            raise ValueError("tool manifest outside tool root")
        manifest = ToolManifest.from_yaml(manifest_path)
        if self._is_forbidden(manifest.name, manifest.permissions):
            raise ValueError("TOOL_FORBIDDEN_ROBOT_CAPABILITY")
        if check_access:
            access = self._check_access(agent_name, manifest.name, permissions, action="install", irreversible=True)
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
                        call_id=str(params.get("call_id") or syscall.syscall_id),
                    )
                )
            if operation == "tool_list":
                return self._kernel_response({"success": True, "tools": self.list_tools()})
            if operation == "tool_describe":
                return self._kernel_response(self.describe(str(params.get("name") or params.get("tool") or "")))
            if operation == "tool_load_manifest":
                manifest_path = str(params.get("path") or "")
                permissions = tuple(params.get("permissions") or ())
                access = self._check_access(syscall.agent_name, manifest_path, permissions, action="install", irreversible=True)
                if not access.get("success", True):
                    return self._kernel_response(
                        self._audit_dangerous_result(
                            "load_manifest",
                            syscall.agent_name,
                            manifest_path,
                            access,
                            manifest_path=manifest_path,
                        )
                    )
                try:
                    manifest = self.load_manifest(
                        manifest_path,
                        agent_name=syscall.agent_name,
                        permissions=permissions,
                        check_access=False,
                    )
                except ValueError as exc:
                    return self._kernel_response(
                        self._audit_dangerous_result(
                            "load_manifest",
                            syscall.agent_name,
                            manifest_path,
                            {"success": False, "error_code": str(exc) or "TOOL_MANIFEST_INVALID"},
                            manifest_path=manifest_path,
                        )
                    )
                return self._kernel_response(
                    self._audit_dangerous_result(
                        "load_manifest",
                        syscall.agent_name,
                        manifest.name,
                        {"success": True, "tool": manifest.name, "manifest": manifest.__dict__},
                        manifest_path=manifest_path,
                    )
                )
            if operation == "tool_unload":
                return self._kernel_response(
                    self.unload(
                        syscall.agent_name,
                        str(params.get("name") or ""),
                        tuple(params.get("permissions") or ()),
                    )
                )
            if operation == "tool_register_builtin":
                return self._kernel_response(
                    self.register_builtin(
                        syscall.agent_name,
                        str(params.get("name") or ""),
                        tuple(params.get("permissions") or ()),
                    )
                )
            if operation == "tool_status":
                call_id = str(params.get("call_id") or params.get("syscall_id") or params.get("correlation_id") or "")
                status = self.status(call_id=call_id)
                if call_id:
                    return self._kernel_response(status)
                return self._kernel_response({"success": True, "status": status})
            if operation == "tool_cancel":
                return self._kernel_response(
                    self.cancel(str(params.get("call_id") or params.get("syscall_id") or params.get("correlation_id") or ""))
                )
            return self._kernel_response(
                self.call_tool(
                    syscall.agent_name,
                    str(params.get("name") or operation),
                    dict(params.get("args") or params.get("parameters") or {}),
                    tuple(params.get("permissions") or ()),
                    call_id=str(params.get("call_id") or syscall.syscall_id),
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
        call_id: str = "",
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
        call_id = call_id or f"tool_{uuid4().hex}"
        cancel_event = Event()
        with self._lock:
            if self._active & conflicts:
                return {"success": False, "error_code": "TOOL_BUSY", "tool": tool_name}
            self._active.update(conflicts)
            self._active_calls[call_id] = _ActiveToolCall(
                call_id=call_id,
                agent_name=agent_name,
                tool_name=tool_name,
                conflicts=set(conflicts),
                cancel_event=cancel_event,
            )
        try:
            self._record_tool_event("tool.started", agent_name, tool_name, {"call_id": call_id})
            result = handler({**tool_args, "_cancel_event": cancel_event})
            if cancel_event.is_set():
                self._record_tool_event("tool.cancelled", agent_name, tool_name, {"call_id": call_id})
                return {
                    "success": False,
                    "error_code": "TOOL_CANCELLED",
                    "tool": tool_name,
                    "call_id": call_id,
                    "result": result,
                }
            return {"success": True, "tool": tool_name, "call_id": call_id, "result": result}
        except Exception as exc:
            self._record_tool_event("tool.failed", agent_name, tool_name, {"reason": str(exc), "call_id": call_id})
            return {"success": False, "error_code": "TOOL_FAILED", "reason": str(exc), "tool": tool_name, "call_id": call_id}
        finally:
            self._record_tool_event("tool.done", agent_name, tool_name, {"call_id": call_id})
            with self._lock:
                self._active.difference_update(conflicts)
                self._active_calls.pop(call_id, None)

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

    def unload(self, agent_name: str, name: str, permissions: tuple[str, ...] = ()) -> dict[str, Any]:
        access = self._check_access(agent_name, name, permissions, action="uninstall", irreversible=True)
        if not access.get("success", True):
            return self._audit_dangerous_result("unload", agent_name, name, access)
        if name not in self._registry:
            return self._audit_dangerous_result(
                "unload",
                agent_name,
                name,
                {"success": False, "error_code": "TOOL_NOT_FOUND", "tool": name},
            )
        if name in builtin_tools(self.tool_root or Path.cwd()):
            return self._audit_dangerous_result(
                "unload",
                agent_name,
                name,
                {"success": False, "error_code": "TOOL_BUILTIN_UNLOAD_DENIED", "tool": name},
            )
        self._registry.pop(name, None)
        self._conflicts.pop(name, None)
        self._descriptions.pop(name, None)
        self._manifests.pop(name, None)
        return self._audit_dangerous_result("unload", agent_name, name, {"success": True, "tool": name})

    def register_builtin(self, agent_name: str, name: str, permissions: tuple[str, ...] = ()) -> dict[str, Any]:
        access = self._check_access(agent_name, name, permissions, action="register_builtin", irreversible=True)
        if not access.get("success", True):
            return self._audit_dangerous_result("register_builtin", agent_name, name, access)
        builtins = builtin_tools(self.tool_root or Path.cwd())
        if name not in builtins:
            return self._audit_dangerous_result(
                "register_builtin",
                agent_name,
                name,
                {"success": False, "error_code": "TOOL_NOT_FOUND", "tool": name},
            )
        handler, description = builtins[name]
        self.register(name, handler, description=description)
        return self._audit_dangerous_result("register_builtin", agent_name, name, {"success": True, "tool": name})

    def cancel(self, call_id: str = "") -> dict[str, Any]:
        if not call_id:
            return {"success": False, "error_code": "SYSCALL_NOT_FOUND", "reason": "call_id required"}
        with self._lock:
            active = self._active_calls.get(call_id)
        if active is None:
            return {"success": False, "error_code": "SYSCALL_NOT_FOUND", "call_id": call_id}
        active.cancel_event.set()
        self._record_tool_event(
            "tool.cancel_requested",
            active.agent_name,
            active.tool_name,
            {"call_id": call_id},
        )
        return {
            "success": True,
            "status": "cancel_requested",
            "cancelled": [call_id],
            "call_id": call_id,
            "tool": active.tool_name,
        }

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
            if irreversible:
                return {
                    "success": False,
                    "error_code": "ACCESS_MANAGER_UNAVAILABLE",
                    "reason": f"tool {action} requires a kernel access manager",
                    "requires_intervention": False,
                }
            return {"success": True}
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(agent_name=agent_name, permissions=permissions),
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

    def status(self, call_id: str = "") -> dict[str, Any]:
        active_calls = [
            {"call_id": call.call_id, "agent_name": call.agent_name, "tool": call.tool_name}
            for call in sorted(self._active_calls.values(), key=lambda item: item.call_id)
        ]
        if call_id:
            match = next((call for call in active_calls if call["call_id"] == call_id), None)
            if match is None:
                result = {
                    "success": False,
                    "error_code": "SYSCALL_NOT_FOUND",
                    "reason": "tool call_id is not active",
                    "call_id": call_id,
                    "active_calls": active_calls,
                }
                self._record_tool_event("tool.status", "", "", result)
                return result
            result = {"success": True, "call_id": call_id, "active_call": match, "active_calls": active_calls}
            self._record_tool_event("tool.status", match["agent_name"], match["tool"], {"call_id": call_id, "success": True})
            return result
        return {
            "tool_count": len(self._registry),
            "active": sorted(self._active),
            "active_calls": active_calls,
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

    def _audit_dangerous_result(
        self,
        action: str,
        agent_name: str,
        tool_name: str,
        result: dict[str, Any],
        **metadata: Any,
    ) -> dict[str, Any]:
        event = {
            "event_type": "tool.audit",
            "agent_name": agent_name,
            "action": action,
            "tool": tool_name,
            "success": bool(result.get("success", False)),
            "error_code": str(result.get("error_code") or ""),
            "irreversible": True,
            "provider": "local_tool_manager",
            **metadata,
        }
        self._audit_events.append(event)
        self._audit_events = self._audit_events[-100:]
        if self.event_sink is not None:
            self.event_sink.emit(
                "tool.audit",
                agent_name=agent_name,
                action=action,
                tool=tool_name,
                success=event["success"],
                error_code=event["error_code"],
                irreversible=True,
                provider="local_tool_manager",
                **metadata,
            )
        return result

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
            self.event_sink.emit(event_type, agent_name=agent_name, tool=tool_name, **dict(metadata or {}))
