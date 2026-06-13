from __future__ import annotations

import asyncio
from typing import Awaitable, TypeVar

from agentic_runtime.errors import SkillTimeoutError

T = TypeVar("T")


async def run_with_timeout(awaitable: Awaitable[T], timeout_s: int) -> T:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        raise SkillTimeoutError(f"skill timed out after {timeout_s}s") from exc
