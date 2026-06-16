from __future__ import annotations

from agentic_runtime.sdk import AgentContext


class AgenticOSTools:
    """AIOS-style tool wrappers backed only by AgenticOS SDK calls."""

    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    async def perception_capture_photo(self, target: str = "workspace", label: str = "photo", timeout_s: int = 5) -> dict:
        return (await self.ctx.perception.capture_photo(target=target, label=label, timeout_s=timeout_s)).to_dict()

    async def arm_move_named(self, name: str, timeout_s: int = 8) -> dict:
        return (await self.ctx.arm.move_named(name=name, timeout_s=timeout_s)).to_dict()

    async def robot_stop(self, reason: str = "tool_requested_stop") -> dict:
        return (await self.ctx.robot.stop(reason=reason)).to_dict()

    async def robot_status(self) -> dict:
        robot = await self.ctx.robot.get_state()
        arm = await self.ctx.arm.get_state()
        return {"robot": robot.to_dict(), "arm": arm.to_dict()}

    async def recent_photos(self, limit: int = 5) -> dict:
        return {"photos": await self.ctx.storage.list_recent_photos(limit=limit)}
