from __future__ import annotations

from agentic_runtime.skill_executor.executor import raise_for_result


class MemoryAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def remember(self, key: str, value):
        result = await self.ctx.call_skill("memory.remember", {"key": key, "value": value})
        raise_for_result(result)
        return result

    async def recall(self, key: str, default=None):
        result = await self.ctx.call_skill("memory.recall", {"key": key})
        raise_for_result(result)
        value = result.data.get("value")
        return default if value is None else value
