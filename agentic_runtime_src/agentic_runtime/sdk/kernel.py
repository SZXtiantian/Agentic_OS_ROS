from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call import LLMQuery, MemoryQuery, StorageQuery, ToolQuery

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


class KernelMemoryAPI(_KernelBaseAPI):
    async def add(self, content, key: str = "", **metadata):
        query = MemoryQuery(
            operation_type="remember",
            params={"memory_id": key, "content": content, "metadata": metadata},
        )
        return self._execute(query, timeout_s=metadata.get("timeout_s"))

    async def search(self, query: str, limit: int = 5, **filters):
        params = {"query": query, "limit": int(limit)}
        if filters:
            params["filters"] = filters
        return self._execute(MemoryQuery(operation_type="search", params=params), timeout_s=filters.get("timeout_s"))


class KernelStorageAPI(_KernelBaseAPI):
    async def write(self, path: str, content, **metadata):
        query = StorageQuery(operation_type="sto_write", params={"path": path, "content": content, "metadata": metadata})
        return self._execute(query, timeout_s=metadata.get("timeout_s"))

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
