from __future__ import annotations

from typing import Protocol


class BridgeTransport(Protocol):
    async def request(self, capability: str, payload: dict) -> dict: ...
