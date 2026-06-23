from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call import (
    ContextQuery,
    KernelResponse,
    LLMQuery,
    MemoryQuery,
    SkillQuery,
    StorageQuery,
    ToolQuery,
)

from .access import KernelAccessAPI


@dataclass
class KernelSDKResult:
    success: bool
    response: Any = None
    error_code: str = ""
    syscall_id: str = ""
    audit_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @classmethod
    def from_execution_result(cls, result) -> "KernelSDKResult":
        metadata = dict(getattr(result, "metadata", {}) or {})
        syscall = getattr(result, "syscall", None)
        syscall_id = str(getattr(syscall, "syscall_id", "") or metadata.get("syscall_id", ""))
        audit_id = str(metadata.get("audit_id", ""))
        return cls(
            success=bool(getattr(result, "success", False)),
            response=getattr(result, "response", None),
            error_code=str(getattr(result, "error_code", "")),
            syscall_id=syscall_id,
            audit_id=audit_id,
            metadata=metadata,
            raw=result,
        )

    @classmethod
    def from_kernel_response(cls, response: KernelResponse) -> "KernelSDKResult":
        metadata = dict(response.metadata or {})
        return cls(
            success=response.success,
            response=response,
            error_code=response.error_code,
            syscall_id=str(metadata.get("syscall_id", "")),
            audit_id=str(metadata.get("audit_id", "")),
            metadata=metadata,
            raw=response,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KernelAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.llm = KernelLLMAPI(ctx)
        self.context = KernelContextAPI(ctx)
        self.memory = KernelMemoryAPI(ctx)
        self.storage = KernelStorageAPI(ctx)
        self.skill = KernelSkillAPI(ctx)
        self.tool = KernelToolAPI(ctx)
        self.access = KernelAccessAPI(ctx)

    def status(self) -> dict:
        service = self.ctx.kernel_service
        if service is None:
            raise RuntimeError("kernel service is not available on this AgentContext")
        return service.status()

    async def cancel(self, syscall_id: str = "") -> KernelSDKResult:
        service = self.ctx.kernel_service
        if service is None:
            raise RuntimeError("kernel service is not available on this AgentContext")
        return KernelSDKResult.from_kernel_response(service.cancel_request(syscall_id))


class _KernelBaseAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    def _execute(self, query, timeout_s=None):
        service = self.ctx.kernel_service
        if service is None:
            raise RuntimeError("kernel service is not available on this AgentContext")
        return KernelSDKResult.from_execution_result(
            service.execute_request(self.ctx.app_manifest.name, query, timeout_s=timeout_s)
        )


class KernelLLMAPI(_KernelBaseAPI):
    def _metadata(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(kwargs.get("metadata") or {})
        permissions = kwargs.get("permissions", tuple(getattr(self.ctx.app_manifest, "permissions", ())))
        metadata.setdefault("permissions", tuple(permissions))
        metadata.setdefault("app_id", self.ctx.app_manifest.name)
        metadata.setdefault("session_id", self.ctx.session_id)
        return metadata

    async def chat(self, messages: list[dict], **kwargs):
        query = LLMQuery(
            operation_type="llm_chat",
            messages=list(messages),
            tools=kwargs.get("tools"),
            selected_llms=kwargs.get("selected_llms"),
            response_format=kwargs.get("response_format"),
            params=dict(kwargs.get("params") or {}),
            metadata=self._metadata(kwargs),
            action_type="chat",
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def complete(self, prompt: str, **kwargs):
        query = LLMQuery(
            operation_type="llm_complete",
            params={"prompt": prompt, **dict(kwargs.get("params") or {})},
            selected_llms=kwargs.get("selected_llms"),
            response_format=kwargs.get("response_format"),
            metadata=self._metadata(kwargs),
            action_type="complete",
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def embed(self, texts, **kwargs):
        query = LLMQuery(
            operation_type="llm_embed",
            params={"texts": texts},
            selected_llms=kwargs.get("selected_llms"),
            metadata=self._metadata(kwargs),
            action_type="embed",
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def status(self, call_id: str = "", **kwargs):
        query = LLMQuery(operation_type="llm_status", params={"call_id": call_id}, action_type="status")
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def cancel(self, call_id: str = "", **kwargs):
        query = LLMQuery(operation_type="llm_cancel", params={"call_id": call_id}, action_type="cancel")
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))


class KernelContextAPI(_KernelBaseAPI):
    async def snapshot(self, state: dict | None = None, checkpoint: str = "default", **kwargs):
        query = ContextQuery(
            operation_type="ctx_snapshot",
            params={"state": dict(state or {}), "metadata": dict(kwargs.get("metadata") or {})},
            namespace=str(kwargs.get("namespace") or "context"),
            session_id=str(kwargs.get("session_id") or self.ctx.session_id),
            checkpoint=checkpoint,
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def recover(self, session_id: str = "", checkpoint: str = "", **kwargs):
        query = ContextQuery(
            operation_type="ctx_recover",
            params={"checkpoint": checkpoint},
            namespace=str(kwargs.get("namespace") or "context"),
            session_id=session_id or self.ctx.session_id,
            checkpoint=checkpoint,
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def put(self, key: str, value, **kwargs):
        params = {"key": key, "value": value, "metadata": dict(kwargs.get("metadata") or {})}
        if "ttl_s" in kwargs:
            params["ttl_s"] = kwargs["ttl_s"]
        query = ContextQuery(
            operation_type="ctx_put",
            params=params,
            namespace=str(kwargs.get("namespace") or "context"),
            session_id=str(kwargs.get("session_id") or self.ctx.session_id),
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def get(self, key: str, **kwargs):
        query = ContextQuery(
            operation_type="ctx_get",
            params={"key": key},
            namespace=str(kwargs.get("namespace") or "context"),
            session_id=str(kwargs.get("session_id") or self.ctx.session_id),
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def delete(self, key: str, **kwargs):
        query = ContextQuery(
            operation_type="ctx_delete",
            params={"key": key},
            namespace=str(kwargs.get("namespace") or "context"),
            session_id=str(kwargs.get("session_id") or self.ctx.session_id),
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def list(self, prefix: str = "", limit: int = 100, **kwargs):
        query = ContextQuery(
            operation_type="ctx_list",
            params={"prefix": prefix, "limit": int(limit)},
            namespace=str(kwargs.get("namespace") or "context"),
            session_id=str(kwargs.get("session_id") or self.ctx.session_id),
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def compact(self, max_tokens: int = 2000, **kwargs):
        query = ContextQuery(
            operation_type="ctx_compact",
            params={"max_tokens": int(max_tokens)},
            namespace=str(kwargs.get("namespace") or "context"),
            session_id=str(kwargs.get("session_id") or self.ctx.session_id),
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def clear(self, scope: str = "session", **kwargs):
        query = ContextQuery(
            operation_type="ctx_clear",
            params={"scope": scope},
            namespace=str(kwargs.get("namespace") or "context"),
            session_id=str(kwargs.get("session_id") or self.ctx.session_id),
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))


class KernelMemoryAPI(_KernelBaseAPI):
    async def remember(self, content, key: str = "", **metadata):
        return await self.add(content, key=key, **metadata)

    async def add(self, content, key: str = "", **metadata):
        timeout_s = metadata.pop("timeout_s", None)
        query = MemoryQuery(
            operation_type="mem_remember",
            params={"memory_id": key, "content": content, "metadata": metadata},
        )
        return self._execute(query, timeout_s=timeout_s)

    async def search(self, query: str, limit: int = 5, **filters):
        timeout_s = filters.pop("timeout_s", None)
        params = {"query": query, "limit": int(limit)}
        if filters:
            params["filters"] = filters
        return self._execute(MemoryQuery(operation_type="mem_search", params=params), timeout_s=timeout_s)

    async def get(self, key: str, **kwargs):
        query = MemoryQuery(operation_type="mem_get", params={"memory_id": key})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def update(self, key: str, content, **metadata):
        timeout_s = metadata.pop("timeout_s", None)
        query = MemoryQuery(
            operation_type="mem_update",
            params={"memory_id": key, "content": content, "metadata": metadata},
        )
        return self._execute(query, timeout_s=timeout_s)

    async def delete(self, key: str, **kwargs):
        query = MemoryQuery(operation_type="mem_delete", params={"memory_id": key})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def list(self, limit: int = 100, **kwargs):
        query = MemoryQuery(operation_type="mem_list", params={"limit": int(limit)})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def export(self, path: str, **kwargs):
        query = MemoryQuery(operation_type="mem_export", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def import_(self, path: str, **kwargs):
        query = MemoryQuery(operation_type="mem_import", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))


class KernelStorageAPI(_KernelBaseAPI):
    async def mount(self, collection_name: str = "default", **kwargs):
        query = StorageQuery(operation_type="sto_mount", params={"collection_name": collection_name})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def mkdir(self, path: str, **kwargs):
        query = StorageQuery(operation_type="sto_mkdir", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def create_file(self, path: str, **kwargs):
        query = StorageQuery(operation_type="sto_create_file", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def write(self, path: str, content, **metadata):
        timeout_s = metadata.pop("timeout_s", None)
        query = StorageQuery(operation_type="sto_write", params={"path": path, "content": content, "metadata": metadata})
        return self._execute(query, timeout_s=timeout_s)

    async def read(self, path: str, **kwargs):
        query = StorageQuery(operation_type="sto_read", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def list(self, path: str = ".", **kwargs):
        query = StorageQuery(operation_type="sto_list", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def delete(self, path: str, **kwargs):
        query = StorageQuery(operation_type="sto_delete", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def stat(self, path: str, **kwargs):
        query = StorageQuery(operation_type="sto_stat", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def history(self, path: str, **kwargs):
        query = StorageQuery(operation_type="sto_history", params={"path": path})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def rollback(self, path: str, version: str = "", **kwargs):
        query = StorageQuery(operation_type="sto_rollback", params={"path": path, "version": version})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def share(self, path: str, **metadata):
        timeout_s = metadata.pop("timeout_s", None)
        query = StorageQuery(operation_type="sto_share", params={"path": path, "metadata": metadata})
        return self._execute(query, timeout_s=timeout_s)

    async def index(self, collection_name: str = "", **kwargs):
        query = StorageQuery(operation_type="sto_index", params={"collection_name": collection_name})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def retrieve(self, query: str, collection_name: str = "", limit: int = 5):
        return self._execute(
            StorageQuery(
                operation_type="sto_retrieve",
                params={"query": query, "collection_name": collection_name, "limit": int(limit)},
            )
        )


class KernelToolAPI(_KernelBaseAPI):
    def _permissions(self, metadata: dict[str, Any]) -> tuple[str, ...]:
        return tuple(metadata.pop("permissions", tuple(getattr(self.ctx.app_manifest, "permissions", ()))))

    async def call(self, name: str, args: dict | None = None, **metadata):
        timeout_s = metadata.pop("timeout_s", None)
        permissions = self._permissions(metadata)
        query = ToolQuery(
            operation_type="tool_call",
            params={"name": name, "args": dict(args or {}), "permissions": permissions, **metadata},
        )
        return self._execute(query, timeout_s=timeout_s)

    async def list(self, **kwargs):
        query = ToolQuery(operation_type="tool_list", params={})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def describe(self, name: str, **kwargs):
        query = ToolQuery(operation_type="tool_describe", params={"name": name})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def load_manifest(self, path: str, **metadata):
        timeout_s = metadata.pop("timeout_s", None)
        permissions = self._permissions(metadata)
        query = ToolQuery(operation_type="tool_load_manifest", params={"path": path, "permissions": permissions, **metadata})
        return self._execute(query, timeout_s=timeout_s)

    async def unload(self, name: str, **metadata):
        timeout_s = metadata.pop("timeout_s", None)
        permissions = self._permissions(metadata)
        query = ToolQuery(operation_type="tool_unload", params={"name": name, "permissions": permissions, **metadata})
        return self._execute(query, timeout_s=timeout_s)

    async def register_builtin(self, name: str, **metadata):
        timeout_s = metadata.pop("timeout_s", None)
        permissions = self._permissions(metadata)
        query = ToolQuery(operation_type="tool_register_builtin", params={"name": name, "permissions": permissions, **metadata})
        return self._execute(query, timeout_s=timeout_s)

    async def status(self, call_id: str = "", **kwargs):
        query = ToolQuery(operation_type="tool_status", params={"call_id": call_id})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def cancel(self, call_id: str, **kwargs):
        query = ToolQuery(operation_type="tool_cancel", params={"call_id": call_id})
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))


class KernelSkillAPI(_KernelBaseAPI):
    async def call(self, name: str, args: dict | None = None, **kwargs):
        timeout_s = kwargs.pop("timeout_s", None)
        permissions = tuple(kwargs.pop("permissions", tuple(getattr(self.ctx.app_manifest, "permissions", ()))))
        call_id = str(kwargs.pop("call_id", ""))
        query = SkillQuery(
            operation_type="skill_call",
            skill_name=name,
            call_id=call_id,
            app_id=self.ctx.app_manifest.name,
            session_id=self.ctx.session_id,
            params={"args": dict(args or {}), "permissions": permissions, "call_id": call_id, **kwargs},
        )
        return self._execute(query, timeout_s=timeout_s)

    async def list(self, **kwargs):
        query = SkillQuery(operation_type="skill_list", app_id=self.ctx.app_manifest.name, session_id=self.ctx.session_id)
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def describe(self, name: str, **kwargs):
        query = SkillQuery(
            operation_type="skill_describe",
            skill_name=name,
            app_id=self.ctx.app_manifest.name,
            session_id=self.ctx.session_id,
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def status(self, call_id: str = "", **kwargs):
        query = SkillQuery(
            operation_type="skill_status",
            call_id=call_id,
            app_id=self.ctx.app_manifest.name,
            session_id=self.ctx.session_id,
            params={"call_id": call_id},
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))

    async def cancel(self, call_id: str = "", **kwargs):
        query = SkillQuery(
            operation_type="skill_cancel",
            call_id=call_id,
            app_id=self.ctx.app_manifest.name,
            session_id=self.ctx.session_id,
            params={"call_id": call_id},
        )
        return self._execute(query, timeout_s=kwargs.get("timeout_s"))
