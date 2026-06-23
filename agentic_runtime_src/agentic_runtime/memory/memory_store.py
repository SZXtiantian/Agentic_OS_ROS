from __future__ import annotations

from typing import Any, Protocol


class MemoryStore(Protocol):
    def remember(self, app_id: str, session_id: str, key: str, value: Any) -> dict[str, Any]: ...

    def recall(self, app_id: str, key: str) -> Any: ...
