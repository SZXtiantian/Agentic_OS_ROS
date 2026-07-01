from __future__ import annotations

from typing import Any

from agentic_runtime.types import SkillManifest

from .context import SkillRuntimeContext
from .ros2_client import Ros2SkillRuntimeClient
from .ros2_service_runner import _invoke_client_method


class Ros2ActionSkillRunner:
    async def run(self, skill: SkillManifest, args: dict[str, Any], context: SkillRuntimeContext) -> dict[str, Any]:
        if context.cancel_event is not None and context.cancel_event.is_set():
            return {"success": False, "error_code": "SKILL_CANCELLED", "reason": "skill cancelled before dispatch"}
        method_result = await _invoke_client_method(skill, args, context)
        if method_result is not None:
            return method_result
        client = context.bridge_client
        if not hasattr(client, "run_action_skill"):
            if isinstance(client, Ros2SkillRuntimeClient):
                pass
            else:
                return {
                    "success": False,
                    "error_code": "SKILL_BACKEND_UNAVAILABLE",
                    "reason": "bridge client does not implement generic ROS2 action skill execution",
                }
        return await client.run_action_skill(
            skill.implementation,
            args,
            call_id=context.call_id,
            timeout_s=int(args.get("timeout_s") or skill.timeout_s),
        )
