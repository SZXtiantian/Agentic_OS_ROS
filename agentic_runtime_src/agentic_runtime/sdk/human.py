from __future__ import annotations

from agentic_runtime.skill_executor.executor import raise_for_result
from agentic_runtime.types import HumanAnswer


class HumanAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def ask(
        self,
        question: str,
        options=None,
        timeout_s: int = 60,
        require_confirmation: bool = False,
    ) -> HumanAnswer:
        result = await self.ctx.call_skill(
            "human.ask",
            {
                "question": question,
                "options": options or [],
                "timeout_s": timeout_s,
                "require_confirmation": require_confirmation,
            },
        )
        raise_for_result(result)
        return HumanAnswer(
            answered=bool(result.data.get("answered", True)),
            answer=str(result.data.get("answer", "")),
            reason=str(result.data.get("reason", "")),
        )
