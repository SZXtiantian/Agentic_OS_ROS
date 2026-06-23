from __future__ import annotations

from typing import Any

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.memory import MemoryManager as KernelMemoryManager
from agentic_os.kernel.memory import MemoryNote
from agentic_os.kernel.system_call import KernelSyscall

from .provider import MemoryProvider


class RuntimeMemoryProviderAdapter:
    """Adapt the runtime SQLite key/value provider to the AgenticOS kernel memory ABI."""

    def __init__(self, provider: MemoryProvider) -> None:
        self.provider = provider

    def add_memory(self, note: MemoryNote) -> dict[str, Any]:
        session_id = str(note.metadata.get("session_id") or "")
        result = self.provider.remember(note.owner_agent, session_id, note.id, note.content)
        if isinstance(result, dict):
            if not result.get("success", False):
                return {"memory_id": note.id, **result}
            return {"success": True, "memory_id": note.id, **result}
        return {"success": True, "memory_id": note.id}

    def remove_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        deleted = self.provider.delete(agent_name, memory_id)
        return {"success": deleted, "memory_id": memory_id, "error_code": "" if deleted else "MEMORY_NOT_FOUND"}

    def update_memory(self, note: MemoryNote) -> dict[str, Any]:
        session_id = str(note.metadata.get("session_id") or "")
        if self.provider.recall(note.owner_agent, note.id) is None:
            return {"success": False, "memory_id": note.id, "error_code": "MEMORY_NOT_FOUND"}
        result = self.provider.remember(note.owner_agent, session_id, note.id, note.content)
        if isinstance(result, dict):
            if not result.get("success", False):
                return {"memory_id": note.id, **result}
            return {"success": True, "memory_id": note.id, **result}
        return {"success": True, "memory_id": note.id}

    def get_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        value = self.provider.recall(agent_name, memory_id)
        if value is None:
            return {"success": False, "error_code": "MEMORY_NOT_FOUND"}
        return {"success": True, "memory": {"id": memory_id, "content": value, "owner_agent": agent_name}}

    def retrieve_memory(self, query: str, agent_name: str, limit: int = 5, user_id: str = "") -> dict[str, Any]:
        del user_id
        rows = self.provider.search(agent_name, query, limit=limit)
        memories = [
            {
                "id": row["key"],
                "content": row["value"],
                "owner_agent": agent_name,
                "updated_at": row.get("updated_at", ""),
            }
            for row in rows
        ]
        return {"success": True, "memories": memories}


class MemoryManager:
    def __init__(
        self,
        provider: MemoryProvider,
        *,
        access_manager: AccessManager | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.provider = provider
        self.kernel_provider = RuntimeMemoryProviderAdapter(provider)
        self.kernel = KernelMemoryManager(self.kernel_provider, access_manager=access_manager, event_sink=event_sink)

    def remember(self, app_id: str, session_id: str, key: str, value: Any) -> dict[str, Any]:
        return self._response_dict(
            self.kernel.address_request(
                KernelSyscall.create(
                    app_id,
                    "memory",
                    "remember",
                    {
                        "memory_id": key,
                        "content": value,
                        "metadata": {"session_id": session_id, "owner_agent": app_id},
                    },
                )
            )
        )

    def recall(self, app_id: str, key: str) -> Any:
        result = self._response_dict(
            self.kernel.address_request(KernelSyscall.create(app_id, "memory", "recall", {"memory_id": key}))
        )
        if not result.get("success"):
            return None
        return (result.get("memory") or {}).get("content")

    def search(self, app_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        result = self._response_dict(
            self.kernel.address_request(
                KernelSyscall.create(app_id, "memory", "search", {"query": query, "limit": limit})
            )
        )
        rows = []
        for memory in result.get("memories", []):
            rows.append(
                {
                    "key": memory.get("id", ""),
                    "value": memory.get("content"),
                    "updated_at": memory.get("updated_at", ""),
                }
            )
        return rows

    def delete(self, app_id: str, key: str) -> bool:
        result = self._response_dict(
            self.kernel.address_request(KernelSyscall.create(app_id, "memory", "delete", {"memory_id": key}))
        )
        return bool(result.get("success"))

    def _response_dict(self, response: Any) -> dict[str, Any]:
        if hasattr(response, "as_mapping"):
            return dict(response.as_mapping())
        if hasattr(response, "data") and isinstance(response.data, dict):
            return dict(response.data)
        if hasattr(response, "response_message") and isinstance(response.response_message, dict):
            return dict(response.response_message)
        if hasattr(response, "success"):
            return {
                "success": bool(getattr(response, "success", False)),
                "error_code": str(getattr(response, "error_code", "") or ""),
                "metadata": dict(getattr(response, "metadata", {}) or {}),
            }
        if isinstance(response, dict):
            return dict(response)
        return {"success": False, "error_code": "MEMORY_RESPONSE_INVALID"}
