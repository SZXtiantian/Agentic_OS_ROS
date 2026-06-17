from __future__ import annotations

from typing import Any


class SemanticFilesystem:
    def __init__(self, storage_manager: Any) -> None:
        self.storage_manager = storage_manager

    def retrieve(self, query: str, collection_name: str = "", limit: int = 5) -> dict[str, Any]:
        return self.storage_manager.retrieve(query=query, collection_name=collection_name, limit=limit)
