from __future__ import annotations

import json
from typing import Any

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.provider_contracts import ros_bridge_contract
from agentic_runtime.ros_bridge_client.cli_client import (
    Ros2CliBridgeClient,
    RosBridgeCommandError,
    _decode_json_field,
    _decode_list_field,
    _parse_required_response,
)
from agentic_runtime.types import new_id


class SkillRuntimeCommandError(RosBridgeCommandError):
    pass


class SkillProviderTransportUnsupportedError(RuntimeError):
    error_code = "ROS_BRIDGE_MODE_UNSUPPORTED"

    def __init__(self, transport: str) -> None:
        self.transport = transport
        self.status = ros_bridge_contract(transport)
        super().__init__(f"{self.error_code}: unsupported skill provider transport: {transport}")


class Ros2SkillRuntimeClient(Ros2CliBridgeClient):
    async def run_service_skill(
        self,
        implementation: dict[str, Any],
        args: dict[str, Any],
        *,
        call_id: str = "",
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        service = str(implementation.get("service") or "")
        service_type = str(implementation.get("service_type") or "")
        if not service or not service_type:
            return {
                "success": False,
                "error_code": "SKILL_BACKEND_UNAVAILABLE",
                "reason": "ros2_service implementation requires service and service_type",
            }
        payload = _payload_from_args(implementation, args, call_id=call_id)
        try:
            output = await self._service_call(service, service_type, payload, timeout_s)
            data = _parse_required_response(output)
        except RosBridgeCommandError as exc:
            return {"success": False, "error_code": exc.error_code, "reason": exc.reason}
        return _normalize_ros_result(data, implementation)

    async def run_action_skill(
        self,
        implementation: dict[str, Any],
        args: dict[str, Any],
        *,
        call_id: str = "",
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        action = str(implementation.get("action") or "")
        action_type = str(implementation.get("action_type") or "")
        if not action or not action_type:
            return {
                "success": False,
                "error_code": "SKILL_BACKEND_UNAVAILABLE",
                "reason": "ros2_action implementation requires action and action_type",
            }
        payload = _payload_from_args(implementation, args, call_id=call_id)
        try:
            output = await self._action_send_goal(action, action_type, payload, timeout_s)
            data = _parse_required_response(output)
        except RosBridgeCommandError as exc:
            return {"success": False, "error_code": exc.error_code, "reason": exc.reason}
        return _normalize_ros_result(data, implementation)


def create_skill_runtime_client(config: RuntimeConfig):
    transport = _configured_transport(config)
    if transport == "cli":
        return Ros2SkillRuntimeClient()
    raise SkillProviderTransportUnsupportedError(transport)


def _configured_transport(config: RuntimeConfig) -> str:
    provider_transport = str(getattr(config, "skill_provider_transport", "cli") or "cli")
    legacy_transport = str(getattr(config, "ros_bridge_mode", provider_transport) or provider_transport)
    if provider_transport != "cli":
        return provider_transport
    return legacy_transport


def _payload_from_args(implementation: dict[str, Any], args: dict[str, Any], *, call_id: str = "") -> dict[str, Any]:
    payload = dict(implementation.get("payload_defaults") or {})
    payload.update(args)
    request_id_field = str(implementation.get("request_id_field") or "")
    if request_id_field and not payload.get(request_id_field):
        payload[request_id_field] = call_id or new_id("skill")
    for payload_field, arg_field in dict(implementation.get("json_payload_fields") or {}).items():
        payload[payload_field] = json.dumps(args.get(str(arg_field), {}), ensure_ascii=False, sort_keys=True)
    return payload


def _normalize_ros_result(data: dict[str, Any], implementation: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    for output_field, source_field in dict(implementation.get("json_output_fields") or {}).items():
        result[output_field] = _decode_json_field(result.get(str(source_field)))
    for output_field, source_field in dict(implementation.get("list_output_fields") or {}).items():
        result[output_field] = _decode_list_field(result.get(str(source_field)))
    if "success" not in result:
        if "allowed" in result:
            result["success"] = bool(result.get("allowed"))
        elif "answered" in result:
            result["success"] = bool(result.get("answered"))
    return result
