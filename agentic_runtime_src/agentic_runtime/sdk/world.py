from __future__ import annotations

from agentic_runtime.skill_executor.executor import raise_for_result
from agentic_runtime.types import PlaceRef


class WorldAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def resolve_place(self, name: str) -> PlaceRef:
        result = await self.ctx.call_skill("world.resolve_place", {"name": name})
        raise_for_result(result)
        return PlaceRef(**result.data["place"])

    async def get_places(self):
        return []

    async def locate_user(self):
        return None
