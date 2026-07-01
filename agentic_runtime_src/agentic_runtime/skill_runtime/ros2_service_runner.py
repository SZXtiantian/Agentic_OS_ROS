from __future__ import annotations

import inspect
from typing import Any

from agentic_runtime.types import SkillManifest

from .context import SkillRuntimeContext
from .ros2_client import Ros2SkillRuntimeClient


class Ros2ServiceSkillRunner:
    async def run(self, skill: SkillManifest, args: dict[str, Any], context: SkillRuntimeContext) -> dict[str, Any]:
        method_result = await _invoke_client_method(skill, args, context)
        if method_result is not None:
            return method_result
        client = context.bridge_client
        if not hasattr(client, "run_service_skill"):
            if isinstance(client, Ros2SkillRuntimeClient):
                pass
            else:
                return {
                    "success": False,
                    "error_code": "SKILL_BACKEND_UNAVAILABLE",
                    "reason": "bridge client does not implement generic ROS2 service skill execution",
                }
        return await client.run_service_skill(
            skill.implementation,
            args,
            call_id=context.call_id,
            timeout_s=int(args.get("timeout_s") or skill.timeout_s),
        )


async def _invoke_client_method(
    skill: SkillManifest,
    args: dict[str, Any],
    context: SkillRuntimeContext,
) -> dict[str, Any] | None:
    method_name = str(skill.implementation.get("client_method") or "")
    if not method_name:
        return None
    method = getattr(context.bridge_client, method_name, None)
    if not callable(method):
        return None
    kwargs = dict(skill.implementation.get("client_defaults") or {})
    kwargs.update(args)
    signature = inspect.signature(method)
    accepted: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        if name == "cancel_event":
            accepted[name] = context.cancel_event
            continue
        if name == "request_id":
            accepted[name] = kwargs.get(name) or context.call_id
            continue
        if name in kwargs:
            accepted[name] = kwargs[name]
        elif parameter.default is inspect.Parameter.empty:
            return {
                "success": False,
                "error_code": "SKILL_BACKEND_UNAVAILABLE",
                "reason": f"client method {method_name} missing required argument {name}",
            }
    result = method(**accepted)
    if inspect.isawaitable(result):
        result = await result
    return result if isinstance(result, dict) else {
        "success": False,
        "error_code": "SKILL_RESULT_INVALID",
        "reason": f"client method {method_name} returned {type(result).__name__}",
    }
