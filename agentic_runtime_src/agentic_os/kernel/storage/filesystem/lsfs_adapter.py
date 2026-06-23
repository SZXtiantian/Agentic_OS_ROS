from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ..manager import StorageManager


class LSFSAdapter:
    def __init__(
        self,
        root: str | Path | None = None,
        use_vector_db: bool = False,
        embedding_provider: Any | None = None,
        access_manager: Any | None = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.use_vector_db = use_vector_db
        self.embedding_provider = embedding_provider
        self.root = Path(root) if root is not None else Path(tempfile.gettempdir()) / "agentic_lsfs"
        self.storage = StorageManager(self.root, access_manager=access_manager)

    def mount(self, collection_name: str) -> dict[str, Any]:
        return self.storage.mount(collection_name)

    def create_file(self, path: str) -> dict[str, Any]:
        return self.storage.create_file(path)

    def create_directory(self, path: str) -> dict[str, Any]:
        return self.storage.create_directory(path)

    def write(self, path: str, content: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.storage.write(path, content)
        if result.get("success"):
            result["metadata"] = dict(metadata or {})
        return result

    def retrieve(self, query: str, collection_name: str = "", limit: int = 5) -> dict[str, Any]:
        return self.storage.retrieve(query=query, collection_name=collection_name, limit=limit)

    def rollback(self, path: str) -> dict[str, Any]:
        return self.storage.rollback(path)

    def share(self, path: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.storage.share(path, metadata)

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "implemented": True,
            "root": str(self.root),
            "use_vector_db": self.use_vector_db,
        }
