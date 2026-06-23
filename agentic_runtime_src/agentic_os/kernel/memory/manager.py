from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall

from .base import MemoryProvider
from .block import CompressedMemoryBlock
from .compression import compress_notes, estimate_tokens
from .eviction import choose_notes_for_eviction
from .note import MemoryNote
from .providers import SQLiteMemoryProvider


class MemoryManager:
    """Syscall-facing two-tier memory manager."""

    def __init__(
        self,
        provider: MemoryProvider | None = None,
        persistent_provider: MemoryProvider | None = None,
        access_manager: AccessManager | None = None,
        max_notes_per_agent: int = 100,
        max_blocks_per_agent: int = 100,
        max_ram_tokens_per_agent: int | None = None,
        eviction_policy: str = "oldest",
        two_tier_enabled: bool = False,
        storage_manager: Any | None = None,
        db_path: str | Path | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.provider = provider or SQLiteMemoryProvider(db_path or self._default_db_path())
        self.persistent_provider = persistent_provider
        self.access_manager = access_manager
        self.event_sink = event_sink
        self.max_notes_per_agent = max_notes_per_agent
        self.max_blocks_per_agent = max_blocks_per_agent
        self.max_ram_tokens_per_agent = max_ram_tokens_per_agent
        self.eviction_policy = eviction_policy
        self.two_tier_enabled = two_tier_enabled
        self.storage_manager = storage_manager
        self.compressed_blocks: dict[str, list[CompressedMemoryBlock]] = {}

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        operation = syscall.operation_type
        params = syscall.params
        try:
            if operation in {"mem_add", "mem_remember", "add_memory", "remember"}:
                note = self._note_from_params(syscall.agent_name, params)
                return self._kernel_response(self.add(note, subject_agent=syscall.agent_name))
            if operation in {"mem_delete", "remove_memory", "delete"}:
                result = self.remove(self._memory_id_from_params(params), syscall.agent_name)
                return self._kernel_response(result)
            if operation in {"mem_update", "update_memory"}:
                note = self._note_from_params(syscall.agent_name, params)
                return self._kernel_response(self.update(note, subject_agent=syscall.agent_name))
            if operation in {"mem_get", "get_memory", "recall"}:
                return self._kernel_response(self.get(self._memory_id_from_params(params), syscall.agent_name))
            if operation in {"mem_search", "retrieve_memory", "search"}:
                return self._kernel_response(
                    self.retrieve(
                        syscall.agent_name,
                        str(params.get("query") or params.get("content") or ""),
                        limit=int(params.get("limit", params.get("k", 5))),
                        user_id=str(params.get("user_id", "")),
                    )
                )
            if operation == "mem_list":
                return self._kernel_response(
                    self.list(syscall.agent_name, limit=int(params.get("limit", 100)))
                )
            if operation == "mem_export":
                return self._kernel_response(self.export(syscall.agent_name, str(params.get("path") or "")))
            if operation == "mem_import":
                return self._kernel_response(self.import_(syscall.agent_name, str(params.get("path") or "")))
            return KernelResponse.error("MEMORY_OPERATION_UNSUPPORTED", metadata={"operation": operation})
        except Exception as exc:
            return KernelResponse.error(
                "MEMORY_PROVIDER_UNAVAILABLE",
                metadata={"reason": str(exc), "provider_status": self.status()},
            )

    def add(self, note: MemoryNote, subject_agent: str | None = None) -> dict[str, Any]:
        decision = self._check_access(subject_agent or note.owner_agent, "write", note)
        if not decision.get("success", True):
            return self._audit_result("remember", subject_agent or note.owner_agent, decision, memory_id=note.id)
        result = self.provider.add_memory(note)
        if result.get("success"):
            self._evict_if_needed(note.owner_agent)
        return self._audit_result("remember", subject_agent or note.owner_agent, result, memory_id=note.id)

    def get(self, memory_id: str, agent_name: str) -> dict[str, Any]:
        decision = self._check_read_access(agent_name, memory_id)
        if not decision.get("success", True):
            return self._audit_result("get", agent_name, decision, memory_id=memory_id)
        result = self.provider.get_memory(memory_id, agent_name)
        if not result.get("success") and self.persistent_provider is not None:
            result = self.persistent_provider.get_memory(memory_id, agent_name)
        return self._audit_result("get", agent_name, result, memory_id=memory_id)

    def retrieve(self, agent_name: str, query: str, limit: int = 5, user_id: str = "") -> dict[str, Any]:
        decision = self._check_memory_operation_access(agent_name, "search", query or "*")
        if not decision.get("success", True):
            return self._audit_result("search", agent_name, decision, query=query)
        result = self.provider.retrieve_memory(query, agent_name, limit, user_id)
        if not result.get("success", False):
            return self._audit_result("search", agent_name, result, query=query)
        memories = list(result.get("memories") or [])
        memories.extend(self._retrieve_compressed_blocks(agent_name, query, limit - len(memories)))
        if self.persistent_provider is not None and len(memories) < limit:
            persistent = self.persistent_provider.retrieve_memory(query, agent_name, limit - len(memories), user_id)
            memories.extend(persistent.get("memories") or [])
        if self.two_tier_enabled and self.storage_manager is not None and len(memories) < limit:
            storage_matches = self.storage_manager.retrieve(query, collection_name="memory_blocks", limit=limit - len(memories))
            for match in storage_matches.get("matches", []):
                memories.append(
                    {
                        "id": match.get("relative_path", ""),
                        "content": match.get("content", ""),
                        "owner_agent": agent_name,
                        "metadata": {"source": "storage_memory_block"},
                    }
                )
        return self._audit_result("search", agent_name, {"success": True, "memories": memories[:limit]}, query=query)

    def update(self, note: MemoryNote, subject_agent: str | None = None) -> dict[str, Any]:
        decision = self._check_access(subject_agent or note.owner_agent, "write", note)
        if not decision.get("success", True):
            return self._audit_result("update", subject_agent or note.owner_agent, decision, memory_id=note.id)
        return self._audit_result(
            "update",
            subject_agent or note.owner_agent,
            self.provider.update_memory(note),
            memory_id=note.id,
        )

    def remove(self, memory_id: str, agent_name: str) -> dict[str, Any]:
        if self.access_manager is None:
            return self._audit_dangerous_result(
                "delete",
                agent_name,
                {
                    "success": False,
                    "error_code": "ACCESS_MANAGER_UNAVAILABLE",
                    "reason": "memory delete requires a kernel access manager",
                    "requires_intervention": False,
                },
                memory_id=memory_id,
            )
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(agent_name=agent_name),
                action="delete",
                resource=AccessResource("memory", memory_id, owner_agent=agent_name),
                irreversible=True,
            )
        )
        if not decision.allowed:
            return self._audit_dangerous_result(
                "delete",
                agent_name,
                {
                    "success": False,
                    "error_code": decision.error_code,
                    "reason": decision.reason,
                    "requires_intervention": decision.requires_intervention,
                },
                memory_id=memory_id,
            )
        return self._audit_dangerous_result(
            "delete",
            agent_name,
            self._call_provider_dangerous("delete", self.provider.remove_memory, memory_id, agent_name),
            memory_id=memory_id,
        )

    def list(self, agent_name: str, limit: int = 100) -> dict[str, Any]:
        decision = self._check_memory_operation_access(agent_name, "list", "*")
        if not decision.get("success", True):
            return self._audit_result("list", agent_name, decision)
        if not hasattr(self.provider, "list_notes"):
            return self._audit_result("list", agent_name, {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE"})
        try:
            notes = self.provider.list_notes(agent_name, limit=limit)  # type: ignore[attr-defined]
        except TypeError:
            notes = self.provider.list_notes(agent_name)[:limit]  # type: ignore[attr-defined]
        return self._audit_result("list", agent_name, {"success": True, "memories": [note.to_dict() for note in notes]})

    def export(self, agent_name: str, path: str) -> dict[str, Any]:
        decision = self._check_dangerous_access(agent_name, "export", path)
        if not decision.get("success", True):
            return self._audit_dangerous_result("export", agent_name, decision, export_path=path)
        if not path:
            return self._audit_dangerous_result(
                "export",
                agent_name,
                {"success": False, "error_code": "MEMORY_EXPORT_PATH_REQUIRED"},
                export_path=path,
            )
        if hasattr(self.provider, "export_memories"):
            return self._audit_dangerous_result(
                "export",
                agent_name,
                self._call_provider_dangerous(
                    "export",
                    self.provider.export_memories,  # type: ignore[attr-defined]
                    agent_name,
                    path,
                ),
                export_path=path,
            )
        return self._audit_dangerous_result(
            "export",
            agent_name,
            {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE"},
            export_path=path,
        )

    def import_(self, agent_name: str, path: str) -> dict[str, Any]:
        decision = self._check_dangerous_access(agent_name, "import", path)
        if not decision.get("success", True):
            return self._audit_dangerous_result("import", agent_name, decision, import_path=path)
        if not path:
            return self._audit_dangerous_result(
                "import",
                agent_name,
                {"success": False, "error_code": "MEMORY_IMPORT_PATH_REQUIRED"},
                import_path=path,
            )
        if hasattr(self.provider, "import_memories"):
            return self._audit_dangerous_result(
                "import",
                agent_name,
                self._call_provider_dangerous(
                    "import",
                    self.provider.import_memories,  # type: ignore[attr-defined]
                    agent_name,
                    path,
                ),
                import_path=path,
            )
        return self._audit_dangerous_result(
            "import",
            agent_name,
            {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE"},
            import_path=path,
        )

    def status(self) -> dict[str, Any]:
        if hasattr(self.provider, "status"):
            return self.provider.status()  # type: ignore[attr-defined]
        return {"state": "ready", "provider": self.provider.__class__.__name__}

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

    def _memory_id_from_params(self, params: dict[str, Any]) -> str:
        return str(params.get("memory_id") or params.get("id") or params.get("key") or "")

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

    def _check_read_access(self, agent_name: str, memory_id: str) -> dict[str, Any]:
        if self.access_manager is None:
            return {"success": True}
        probe = self.provider.get_memory(memory_id, "")
        if not probe.get("success", False):
            return {"success": True}
        note = self._note_from_mapping(dict(probe.get("memory") or {}))
        return self._check_access(agent_name, "read", note)

    def _check_memory_operation_access(self, agent_name: str, action: str, resource_id: str) -> dict[str, Any]:
        if self.access_manager is None:
            return {"success": True}
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(agent_name=agent_name),
                action=action,
                resource=AccessResource("memory", resource_id, owner_agent=agent_name),
            )
        )
        if decision.allowed:
            return {"success": True}
        return {"success": False, "error_code": decision.error_code, "reason": decision.reason}

    def _check_dangerous_access(self, agent_name: str, action: str, memory_id: str) -> dict[str, Any]:
        if self.access_manager is None:
            return {
                "success": False,
                "error_code": "ACCESS_MANAGER_UNAVAILABLE",
                "reason": f"memory {action} requires a kernel access manager",
                "requires_intervention": False,
            }
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(agent_name=agent_name),
                action=action,
                resource=AccessResource("memory", memory_id, owner_agent=agent_name),
                irreversible=action in {"delete", "export", "import"},
            )
        )
        if decision.allowed:
            return {"success": True}
        return {
            "success": False,
            "error_code": decision.error_code,
            "reason": decision.reason,
            "requires_intervention": decision.requires_intervention,
        }

    def _audit_dangerous_result(
        self,
        action: str,
        agent_name: str,
        result: dict[str, Any],
        **metadata: Any,
    ) -> dict[str, Any]:
        return self._audit_result(action, agent_name, result, irreversible=True, **metadata)

    def _audit_result(
        self,
        action: str,
        agent_name: str,
        result: dict[str, Any],
        *,
        irreversible: bool = False,
        **metadata: Any,
    ) -> dict[str, Any]:
        if self.event_sink is not None:
            self.event_sink.emit(
                "memory.audit",
                action=action,
                agent_name=agent_name,
                success=bool(result.get("success", False)),
                error_code=str(result.get("error_code") or ""),
                irreversible=irreversible,
                provider=self.provider.__class__.__name__,
                **metadata,
            )
        return result

    def _note_from_mapping(self, data: dict[str, Any]) -> MemoryNote:
        return MemoryNote(
            id=str(data.get("id") or ""),
            content=data.get("content", ""),
            owner_agent=str(data.get("owner_agent") or ""),
            user_id=str(data.get("user_id") or ""),
            context=str(data.get("context") or ""),
            keywords=list(data.get("keywords") or []),
            tags=list(data.get("tags") or []),
            category=str(data.get("category") or ""),
            sharing_policy=str(data.get("sharing_policy") or "private"),
            memory_type=str(data.get("memory_type") or "episodic"),
            metadata=dict(data.get("metadata") or {}),
        )

    def _call_provider_dangerous(self, action: str, fn: Any, *args: Any) -> dict[str, Any]:
        try:
            result = fn(*args)
        except Exception as exc:
            return {
                "success": False,
                "error_code": "MEMORY_PROVIDER_UNAVAILABLE",
                "reason": str(exc),
                "operation": action,
                "provider_status": self._safe_provider_status(),
            }
        if not isinstance(result, dict):
            return {
                "success": False,
                "error_code": "MEMORY_PROVIDER_RESULT_INVALID",
                "reason": f"provider returned {type(result).__name__}",
                "operation": action,
                "provider_status": self._safe_provider_status(),
            }
        return result

    def _safe_provider_status(self) -> dict[str, Any]:
        try:
            return self.status()
        except Exception as exc:
            return {
                "state": "unavailable",
                "provider": self.provider.__class__.__name__,
                "error_code": "MEMORY_PROVIDER_UNAVAILABLE",
                "reason": str(exc),
            }

    def _evict_if_needed(self, owner_agent: str) -> None:
        if not hasattr(self.provider, "list_notes"):
            return
        notes = self.provider.list_notes(owner_agent)  # type: ignore[attr-defined]
        overflow = max(0, len(notes) - self.max_notes_per_agent)
        if self.max_ram_tokens_per_agent is not None:
            total_tokens = sum(estimate_tokens(str(note.content)) for note in notes)
            while overflow < len(notes) and total_tokens > self.max_ram_tokens_per_agent:
                total_tokens -= estimate_tokens(str(notes[overflow].content))
                overflow += 1
        evicted = choose_notes_for_eviction(notes, overflow, self.eviction_policy)
        if evicted:
            self._compress_evicted_notes(owner_agent, evicted)
        for note in evicted:
            if self.persistent_provider is not None:
                self.persistent_provider.add_memory(note)
            self.provider.remove_memory(note.id, owner_agent)

    def _compress_evicted_notes(self, owner_agent: str, notes: list[MemoryNote]) -> None:
        block = compress_notes(owner_agent, notes, session_id=str(notes[0].metadata.get("session_id", "")) if notes else "")
        blocks = self.compressed_blocks.setdefault(owner_agent, [])
        blocks.append(block)
        if len(blocks) > self.max_blocks_per_agent:
            del blocks[: len(blocks) - self.max_blocks_per_agent]
        if self.two_tier_enabled and self.storage_manager is not None:
            relative_path = f"memory_blocks/{owner_agent}/{block.block_id}.json"
            result = self.storage_manager.write(relative_path, block.to_dict())
            if result.get("success"):
                block.storage_ref = relative_path

    def _retrieve_compressed_blocks(self, agent_name: str, query: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        query_text = query.lower()
        matches: list[dict[str, Any]] = []
        for block in self.compressed_blocks.get(agent_name, []):
            haystack = f"{block.summary} {' '.join(block.notes)}".lower()
            if not query_text or query_text in haystack:
                matches.append(
                    {
                        "id": block.block_id,
                        "content": block.summary,
                        "owner_agent": agent_name,
                        "metadata": {"compressed_block": block.to_dict()},
                    }
                )
            if len(matches) >= limit:
                break
        return matches

    def _kernel_response(self, result: dict[str, Any]) -> KernelResponse:
        if result.get("success", False):
            return KernelResponse.ok(result, data=result)
        return KernelResponse.error(str(result.get("error_code") or "MEMORY_PROVIDER_UNAVAILABLE"), metadata=result)

    def _default_db_path(self) -> Path:
        return Path(tempfile.gettempdir()) / f"agentic_kernel_memory_{uuid4().hex}.sqlite3"
