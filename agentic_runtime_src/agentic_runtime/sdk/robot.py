from __future__ import annotations

from agentic_runtime.skill_executor.executor import raise_for_result
from agentic_runtime.types import InspectionResult, RobotState, SkillResult


class RobotAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def get_state(self) -> RobotState:
        result = await self.ctx.call_skill("robot.get_state", {})
        raise_for_result(result)
        return RobotState(**result.data["state"])

    async def navigate_to(self, place: str, timeout_s: int = 120) -> SkillResult:
        result = await self.ctx.call_skill("robot.navigate_to", {"place": place, "timeout_s": timeout_s})
        raise_for_result(result)
        return result

    async def inspect_area(self, place: str, timeout_s: int = 60) -> InspectionResult:
        result = await self.ctx.call_skill("robot.inspect_area", {"place": place, "timeout_s": timeout_s})
        raise_for_result(result)
        return InspectionResult(
            success=True,
            summary=result.data.get("summary", ""),
            objects=list(result.data.get("objects", [])),
            anomalies=list(result.data.get("anomalies", [])),
        )

    async def stop(self, reason: str = "app_requested") -> SkillResult:
        result = await self.ctx.call_skill("robot.stop", {"reason": reason})
        raise_for_result(result)
        return result
