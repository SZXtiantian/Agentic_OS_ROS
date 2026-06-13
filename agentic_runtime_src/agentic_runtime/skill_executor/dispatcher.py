from __future__ import annotations

from typing import Any

from agentic_runtime.ros_bridge_client.types import RosBridgeClient


class SkillDispatcher:
    def __init__(self, bridge_client: RosBridgeClient, memory_store) -> None:
        self.bridge_client = bridge_client
        self.memory_store = memory_store

    async def dispatch(
        self,
        skill_name: str,
        args: dict[str, Any],
        app_id: str,
        session_id: str,
        cancel_event=None,
    ) -> dict[str, Any]:
        if skill_name == "world.resolve_place":
            return await self.bridge_client.resolve_place(args["name"])
        if skill_name == "robot.get_state":
            return await self.bridge_client.get_robot_state()
        if skill_name == "robot.navigate_to":
            return await self.bridge_client.navigate_to(
                args["place"],
                int(args.get("timeout_s", 120)),
                cancel_event=cancel_event,
            )
        if skill_name == "robot.inspect_area":
            return await self.bridge_client.inspect_area(args["place"], int(args.get("timeout_s", 60)))
        if skill_name == "robot.stop":
            return await self.bridge_client.stop_robot(args.get("reason", "app_requested"))
        if skill_name == "memory.remember":
            self.memory_store.remember(app_id, session_id, args["key"], args.get("value"))
            return {"success": True}
        if skill_name == "memory.recall":
            return {"success": True, "value": self.memory_store.recall(app_id, args["key"])}
        if skill_name == "human.ask":
            return await self.bridge_client.ask_human(
                args["question"],
                options=args.get("options"),
                timeout_s=int(args.get("timeout_s", 60)),
                require_confirmation=bool(args.get("require_confirmation", False)),
            )
        if skill_name == "report.say":
            return await self.bridge_client.report_say(args["message"])
        return {"success": False, "error_code": "BACKEND_UNAVAILABLE", "reason": f"no dispatcher for {skill_name}"}
