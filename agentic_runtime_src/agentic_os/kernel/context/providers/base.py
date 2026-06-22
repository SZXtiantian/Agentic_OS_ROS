from __future__ import annotations

from typing import Any, Protocol


class ContextProvider(Protocol):
    def put(self, owner: str, session_id: str, namespace: str, key: str, value: Any, metadata: dict[str, Any]) -> dict[str, Any]:
        ...

    def get(self, owner: str, session_id: str, namespace: str, key: str) -> dict[str, Any] | None:
        ...

    def delete(self, owner: str, session_id: str, namespace: str, key: str) -> bool:
        ...

    def list(self, owner: str, session_id: str, namespace: str, prefix: str = "", limit: int = 100) -> list[dict[str, Any]]:
        ...

    def snapshot(
        self,
        owner: str,
        session_id: str,
        checkpoint: str,
        state: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def recover(self, owner: str, session_id: str, checkpoint: str = "") -> dict[str, Any] | None:
        ...

    def compact(self, owner: str, session_id: str, namespace: str, max_tokens: int) -> dict[str, Any]:
        ...

    def clear(self, owner: str, session_id: str, scope: str, namespace: str = "") -> int:
        ...

    def status(self) -> dict[str, Any]:
        ...
