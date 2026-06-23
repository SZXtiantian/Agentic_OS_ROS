from __future__ import annotations

from typing import Any, Protocol

from agentic_runtime.ros_bridge_client.types import RosBridgeClient


class BridgeTransport(Protocol):
    async def request(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def health_check(self) -> dict[str, Any]: ...


class RosBridgeClientTransport:
    """Generic transport facade over the ROS-free bridge client protocol."""

    transport_kind = "ros2_cli"
    endpoint = "ros2-cli://agentic-bridge"

    def __init__(self, client: RosBridgeClient) -> None:
        self.client = client

    async def request(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        if capability == "world.resolve_place":
            return await self.client.resolve_place(str(payload["name"]))
        if capability == "robot.get_state":
            return await self.client.get_robot_state()
        if capability == "robot.navigate_to":
            return await self.client.navigate_to(str(payload["place"]), int(payload.get("timeout_s", 60)), payload.get("cancel_event"))
        if capability == "robot.inspect_area":
            return await self.client.inspect_area(str(payload["place"]), int(payload.get("timeout_s", 60)))
        if capability == "perception.observe":
            return await self.client.observe(str(payload.get("target", "workspace")), int(payload.get("timeout_s", 10)))
        if capability == "perception.capture_photo":
            return await self.client.capture_photo(
                str(payload.get("target", "workspace")),
                str(payload.get("label", "photo")),
                int(payload.get("timeout_s", 10)),
            )
        if capability == "arm.get_state":
            return await self.client.get_arm_state()
        if capability == "arm.move_named":
            return await self.client.move_arm_named(str(payload["name"]), int(payload.get("timeout_s", 10)), payload.get("cancel_event"))
        if capability == "gripper.set":
            return await self.client.set_gripper(
                str(payload["command"]),
                force=str(payload.get("force", "low")),
                percentage=payload.get("percentage"),
                timeout_s=int(payload.get("timeout_s", 5)),
            )
        if capability == "robot.stop":
            return await self.client.stop_robot(str(payload.get("reason", "app_requested")))
        if capability == "human.ask":
            return await self.client.ask_human(
                str(payload["question"]),
                options=payload.get("options"),
                timeout_s=int(payload.get("timeout_s", 60)),
                require_confirmation=bool(payload.get("require_confirmation", False)),
            )
        if capability == "report.say":
            return await self.client.report_say(str(payload["message"]))
        return {
            "success": False,
            "error_code": "BRIDGE_CAPABILITY_UNSUPPORTED",
            "reason": f"unsupported bridge capability: {capability}",
        }

    async def health_check(self) -> dict[str, Any]:
        state = await self.client.get_robot_state()
        if not isinstance(state, dict):
            return {
                "success": False,
                "error_code": "BRIDGE_HEALTH_RESULT_INVALID",
                "reason": f"bridge health check returned {type(state).__name__}",
                "transport": self.transport_kind,
                "endpoint": self.endpoint,
                "state": {},
            }
        if "success" not in state or not isinstance(state.get("success"), bool):
            return {
                "success": False,
                "error_code": "BRIDGE_HEALTH_RESULT_INVALID",
                "reason": "bridge health check result missing boolean success field",
                "transport": self.transport_kind,
                "endpoint": self.endpoint,
                "state": state,
            }
        success = state["success"]
        error_code = str(state.get("error_code") or "")
        reason = str(state.get("reason") or "")
        if not success and not error_code:
            error_code = "BRIDGE_HEALTH_CHECK_FAILED"
            reason = reason or "bridge health check failed without error_code"
        return {
            "success": success,
            "error_code": error_code,
            "reason": reason,
            "transport": self.transport_kind,
            "endpoint": self.endpoint,
            "state": state,
        }
