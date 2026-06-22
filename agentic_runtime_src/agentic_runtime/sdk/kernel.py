from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call import ContextQuery, LLMQuery, MemoryQuery, StorageQuery, ToolQuery

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KernelAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.llm = KernelLLMAPI(ctx)
        self.context = KernelContextAPI(ctx)
        self.memory = KernelMemoryAPI(ctx)
        self.storage = KernelStorageAPI(ctx)
        self.tool = KernelToolAPI(ctx)
        self.access = KernelAccessAPI(ctx)

    def status(self) -> dict:
        service = self.ctx.kernel_service
        if service is None:
            raise RuntimeError("kernel service is not available on this AgentContext")
        return service.status()


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
    async def chat(self, messages: list[dict], **kwargs):
        query = LLMQuery(
            operation_type="chat",
            messages=list(messages),
            tools=kwargs.get("tools"),
            selected_llms=kwargs.get("selected_llms"),
            response_format=kwargs.get("response_format"),
            params=dict(kwargs.get("params") or {}),
        )
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
    async def call(self, name: str, args: dict | None = None, **metadata):
        query = ToolQuery(operation_type="call_tool", params={"name": name, "args": dict(args or {}), **metadata})
        return self._execute(query, timeout_s=metadata.get("timeout_s"))
