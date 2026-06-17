from __future__ import annotations

from typing import Any
from uuid import uuid4

from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_os.kernel.system_call import KernelSyscall

from .base import MemoryProvider
from .note import MemoryNote
from .providers import InMemoryMemoryProvider


class MemoryManager:
    """Syscall-facing two-tier memory manager."""

    def __init__(
        self,
        provider: MemoryProvider | None = None,
        persistent_provider: MemoryProvider | None = None,
        access_manager: AccessManager | None = None,
        max_notes_per_agent: int = 100,
    ) -> None:
        self.provider = provider or InMemoryMemoryProvider()
        self.persistent_provider = persistent_provider
        self.access_manager = access_manager
        self.max_notes_per_agent = max_notes_per_agent

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        operation = syscall.operation_type
        params = syscall.params
        if operation in {"add_memory", "remember"}:
            note = self._note_from_params(syscall.agent_name, params)
            return self.add(note, subject_agent=syscall.agent_name)
        if operation in {"remove_memory", "delete"}:
            return self.remove(str(params["memory_id"]), syscall.agent_name)
        if operation == "update_memory":
            note = self._note_from_params(syscall.agent_name, params)
            return self.update(note, subject_agent=syscall.agent_name)
        if operation in {"get_memory", "recall"}:
            return self.get(str(params["memory_id"]), syscall.agent_name)
        if operation in {"retrieve_memory", "search"}:
            return self.retrieve(
                syscall.agent_name,
                str(params.get("query") or params.get("content") or ""),
                limit=int(params.get("limit", params.get("k", 5))),
                user_id=str(params.get("user_id", "")),
            )
        return {"success": False, "error_code": "MEMORY_OPERATION_UNSUPPORTED", "operation": operation}

    def add(self, note: MemoryNote, subject_agent: str | None = None) -> dict[str, Any]:
        decision = self._check_access(subject_agent or note.owner_agent, "write", note)
        if not decision.get("success", True):
            return decision
        result = self.provider.add_memory(note)
        if result.get("success"):
            self._evict_if_needed(note.owner_agent)
        return result

    def get(self, memory_id: str, agent_name: str) -> dict[str, Any]:
        result = self.provider.get_memory(memory_id, agent_name)
        if not result.get("success") and self.persistent_provider is not None:
            result = self.persistent_provider.get_memory(memory_id, agent_name)
        return result

    def retrieve(self, agent_name: str, query: str, limit: int = 5, user_id: str = "") -> dict[str, Any]:
        result = self.provider.retrieve_memory(query, agent_name, limit, user_id)
        memories = list(result.get("memories") or [])
        if self.persistent_provider is not None and len(memories) < limit:
            persistent = self.persistent_provider.retrieve_memory(query, agent_name, limit - len(memories), user_id)
            memories.extend(persistent.get("memories") or [])
        return {"success": True, "memories": memories[:limit]}

    def update(self, note: MemoryNote, subject_agent: str | None = None) -> dict[str, Any]:
        decision = self._check_access(subject_agent or note.owner_agent, "write", note)
        if not decision.get("success", True):
            return decision
        return self.provider.update_memory(note)

    def remove(self, memory_id: str, agent_name: str) -> dict[str, Any]:
        if self.access_manager is not None:
            decision = self.access_manager.check(
                AccessRequest(
                    subject=AccessSubject(agent_name=agent_name),
                    action="delete",
                    resource=AccessResource("memory", memory_id, owner_agent=agent_name),
                )
            )
            if not decision.allowed:
                return {"success": False, "error_code": decision.error_code, "reason": decision.reason}
        return self.provider.remove_memory(memory_id, agent_name)

    def _note_from_params(self, agent_name: str, params: dict[str, Any]) -> MemoryNote:
        metadata = dict(params.get("metadata") or {})
        robot_metadata = dict(metadata.get("robot") or params.get("robot_metadata") or {})
        if robot_metadata:
            metadata["robot"] = robot_metadata
        return MemoryNote(
            id=str(params.get("memory_id") or params.get("id") or f"mem_{uuid4().hex}"),
            content=params.get("content", params.get("value", "")),
            owner_agent=str(metadata.get("owner_agent") or params.get("owner_agent") or agent_name),
            user_id=str(metadata.get("user_id") or params.get("user_id") or ""),
            context=str(metadata.get("context") or params.get("context") or ""),
            keywords=list(metadata.get("keywords") or params.get("keywords") or []),
            tags=list(metadata.get("tags") or params.get("tags") or []),
            category=str(metadata.get("category") or params.get("category") or ""),
            sharing_policy=str(metadata.get("sharing_policy") or params.get("sharing_policy") or "private"),
            memory_type=str(metadata.get("memory_type") or params.get("memory_type") or "episodic"),
            metadata=metadata,
        )

    def _check_access(self, subject_agent: str, action: str, note: MemoryNote) -> dict[str, Any]:
        if self.access_manager is None:
            return {"success": True}
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(agent_name=subject_agent),
                action=action,
                resource=AccessResource(
                    "memory",
                    note.id,
                    owner_agent=note.owner_agent,
                    owner_user=note.user_id,
                    labels=(note.sharing_policy,),
                ),
            )
        )
        if decision.allowed:
            return {"success": True}
        return {"success": False, "error_code": decision.error_code, "reason": decision.reason}

    def _evict_if_needed(self, owner_agent: str) -> None:
        if self.persistent_provider is None or not hasattr(self.provider, "list_notes"):
            return
        notes = self.provider.list_notes(owner_agent)  # type: ignore[attr-defined]
        overflow = max(0, len(notes) - self.max_notes_per_agent)
        for note in notes[:overflow]:
            self.persistent_provider.add_memory(note)
            self.provider.remove_memory(note.id, owner_agent)
