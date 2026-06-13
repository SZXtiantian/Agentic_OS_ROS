from __future__ import annotations

from agentic_runtime.skill_executor.executor import raise_for_result


class ReportAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def say(self, message: str):
        result = await self.ctx.call_skill("report.say", {"message": message})
        raise_for_result(result)
        return result

    async def log(self, message: str, level: str = "info"):
        return await self.say(f"[{level}] {message}")
