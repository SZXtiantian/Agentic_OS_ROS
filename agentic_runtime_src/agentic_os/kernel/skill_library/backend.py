from __future__ import annotations

import asyncio
from typing import Any

from agentic_runtime.types import AppManifest


class RuntimeSkillBackend:
    """Adapter to the real runtime SkillExecutor/SkillRegistry."""

    def __init__(self, runtime_server: Any | None) -> None:
        self.runtime_server = runtime_server

    def call(
        self,
        skill_name: str,
        args: dict[str, Any],
        *,
        app_id: str,
        session_id: str,
        permissions: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if self.runtime_server is None or not hasattr(self.runtime_server, "executor"):
            return self._unavailable("runtime executor not configured")
        app = AppManifest(
            name=app_id,
            version="kernel",
            description="kernel skill request",
            entrypoint="kernel:skill",
            permissions=list(permissions),
            required_capabilities=[],
        )
        try:
            result = self._run(self.runtime_server.executor.execute(app, skill_name, args, session_id))
        except KeyError as exc:
            return {"success": False, "error_code": "SKILL_NOT_FOUND", "reason": str(exc), "skill_name": skill_name}
        except Exception as exc:
            return {"success": False, "error_code": "SKILL_BACKEND_UNAVAILABLE", "reason": str(exc), "skill_name": skill_name}
        payload = result.to_dict()
        return {
            "success": result.success,
            "skill_name": skill_name,
            "result": payload,
            "error_code": result.error_code,
            "reason": result.reason,
            "audit_id": result.audit_id,
        }

    def list(self) -> dict[str, Any]:
        if self.runtime_server is None or not hasattr(self.runtime_server, "registry"):
            return self._unavailable("runtime registry not configured")
        skills = [
            {
                "name": skill.name,
                "description": skill.description,
                "permissions": list(skill.permission_requirements),
                "backend": dict(skill.backend),
            }
            for skill in self.runtime_server.registry.list_skills()
        ]
        return {"success": True, "skills": skills}

    def describe(self, skill_name: str) -> dict[str, Any]:
        if self.runtime_server is None or not hasattr(self.runtime_server, "registry"):
            return self._unavailable("runtime registry not configured")
        try:
            skill = self.runtime_server.registry.get_skill(skill_name)
        except KeyError as exc:
            return {"success": False, "error_code": "SKILL_NOT_FOUND", "reason": str(exc), "skill_name": skill_name}
        return {
            "success": True,
            "skill": {
                "name": skill.name,
                "version": skill.version,
                "description": skill.description,
                "input_schema": dict(skill.input_schema),
                "output_schema": dict(skill.output_schema),
                "permissions": list(skill.permission_requirements),
                "resource_requirements": dict(skill.resource_requirements),
                "safety_constraints": dict(skill.safety_constraints),
                "timeout_s": skill.timeout_s,
                "backend": dict(skill.backend),
            },
        }

    def status(self) -> dict[str, Any]:
        if self.runtime_server is None:
            return self._unavailable("runtime server not configured")
        missing = [name for name in ("executor", "registry") if not hasattr(self.runtime_server, name)]
        if missing:
            return self._unavailable(f"runtime missing {', '.join(missing)}")
        return {"success": True, "state": "ready", "backend": "runtime_skill_executor"}

    def cancel(self, session_id: str, call_id: str = "") -> dict[str, Any]:
        if self.runtime_server is None or not hasattr(self.runtime_server, "executor"):
            return self._unavailable("runtime executor not configured")
        cancellation_manager = getattr(self.runtime_server.executor, "cancellation_manager", None)
        if cancellation_manager is None:
            return {"success": False, "error_code": "SKILL_BACKEND_UNAVAILABLE", "reason": "cancellation manager not configured"}
        cancellation_manager.cancel_session(session_id)
        return {"success": True, "session_id": session_id, "call_id": call_id, "status": "cancel_requested"}

    def _unavailable(self, reason: str) -> dict[str, Any]:
        return {
            "success": False,
            "state": "unavailable",
            "error_code": "SKILL_BACKEND_UNAVAILABLE",
            "reason": reason,
        }

    def _run(self, awaitable):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("RuntimeSkillBackend cannot run inside an active event loop")
