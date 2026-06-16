from __future__ import annotations

from agentic_runtime.skill_executor.executor import raise_for_result


class StorageAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def list_recent_photos(self, limit: int = 5) -> list[dict]:
        result = await self.ctx.call_skill("storage.list_recent_photos", {"limit": int(limit)})
        raise_for_result(result)
        return list(result.data.get("photos", []))
