from __future__ import annotations

from typing import Any

from ..note import MemoryNote


class ChromaMemoryProvider:
    def __init__(self, enabled: bool = False, collection_name: str = "agentic_memory") -> None:
        self.enabled = enabled
        self.collection_name = collection_name
        self._client = None

    def _ensure_client(self):
        if not self.enabled:
            return None
        try:
            import chromadb  # type: ignore[import-not-found]
        except ImportError:
            return None
        if self._client is None:
            self._client = chromadb.Client()
        return self._client

    def add_memory(self, note: MemoryNote) -> dict[str, Any]:
        client = self._ensure_client()
        if client is None:
            return {"success": False, "error_code": "MEMORY_PROVIDER_DEPENDENCY_MISSING", "provider": "chromadb"}
        collection = client.get_or_create_collection(self.collection_name)
        collection.add(ids=[note.id], documents=[str(note.content)], metadatas=[note.metadata])
        return {"success": True, "memory_id": note.id}
