from __future__ import annotations

import inspect
from typing import Any

from agentic_runtime.human_channel import FileHumanQueueChannel
from agentic_runtime.ros_bridge_client.types import RosBridgeClient
from agentic_runtime.skill_runtime import (
    PythonSkillRunner,
    Ros2ActionSkillRunner,
    Ros2ServiceSkillRunner,
    RuntimeInternalSkillRunner,
    SkillRuntimeContext,
)
from agentic_runtime.types import SkillManifest


class SkillDispatcher:
    def __init__(
        self,
        bridge_client: RosBridgeClient,
        memory_store,
        human_channel: FileHumanQueueChannel | None = None,
        runners: dict[str, Any] | None = None,
    ) -> None:
        self.bridge_client = bridge_client
        self.memory_store = memory_store
        self.human_channel = human_channel
        self.runners = runners or {
            "python": PythonSkillRunner(),
            "ros2_service": Ros2ServiceSkillRunner(),
            "ros2_action": Ros2ActionSkillRunner(),
            "runtime_internal": RuntimeInternalSkillRunner(),
        }
    async def dispatch(
        self,
        skill: SkillManifest,
        args: dict[str, Any],
        app_id: str,
        session_id: str,
        cancel_event=None,
        call_id: str = "",
    ) -> dict[str, Any]:
        implementation_type = str(skill.implementation.get("type") or "")
        runner = self.runners.get(implementation_type)
        if runner is None:
            return {
                "success": False,
                "error_code": "BACKEND_UNAVAILABLE",
                "reason": f"no skill runtime runner for implementation.type={implementation_type}",
            }
        context = SkillRuntimeContext(
            app_id=app_id,
            session_id=session_id,
            call_id=call_id,
            cancel_event=cancel_event,
            bridge_client=self.bridge_client,
            memory_store=self.memory_store,
            human_channel=self.human_channel,
        )
        return await runner.run(skill, args, context)

    async def check_safety(self, skill: SkillManifest, args: dict[str, Any], app_id: str) -> dict[str, Any]:
        check = getattr(self.bridge_client, "check_safety", None)
        if not callable(check):
            return {
                "allowed": False,
                "error_code": "SAFETY_BACKEND_UNAVAILABLE",
                "reason": "skill provider transport does not expose safety checks",
            }
        result = check(skill.name, args, app_id)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, dict) else {
            "allowed": False,
            "error_code": "SAFETY_BACKEND_UNAVAILABLE",
            "reason": f"safety check returned {type(result).__name__}",
        }

    async def checkpoint_capability(
        self,
        skill: SkillManifest,
        args: dict[str, Any],
        app_id: str,
        session_id: str,
        *,
        syscall_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checkpoint_method = getattr(self.bridge_client, "checkpoint_capability", None)
        if callable(checkpoint_method):
            result = checkpoint_method(
                skill_name=skill.name,
                args=dict(args),
                app_id=app_id,
                session_id=session_id,
                syscall_id=syscall_id,
                metadata=dict(metadata or {}),
            )
            if inspect.isawaitable(result):
                result = await result
            return result
        checkpoint_method = getattr(self.bridge_client, "checkpoint_request", None)
        if callable(checkpoint_method):
            result = checkpoint_method(syscall_id, skill_name=skill.name, session_id=session_id, metadata=dict(metadata or {}))
            if inspect.isawaitable(result):
                result = await result
            return result
        return {
            "success": False,
            "error_code": "SCHEDULER_PREEMPTION_UNSUPPORTED",
            "reason": "skill provider transport does not expose checkpoint capability",
            "skill_name": skill.name,
            "syscall_id": syscall_id,
        }
