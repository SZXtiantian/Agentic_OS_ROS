from __future__ import annotations

from agentic_os.kernel.system_call import LLMQuery, MemoryQuery, StorageQuery, ToolQuery

from .access import KernelAccessAPI


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
        return service.execute_request(self.ctx.app_manifest.name, query, timeout_s=timeout_s)


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


class KernelStorageAPI(_KernelBaseAPI):
    async def write(self, path: str, content, **metadata):
        query = StorageQuery(operation_type="sto_write", params={"path": path, "content": content, "metadata": metadata})
        return self._execute(query, timeout_s=metadata.get("timeout_s"))


class KernelToolAPI(_KernelBaseAPI):
    async def call(self, name: str, args: dict | None = None, **metadata):
        query = ToolQuery(operation_type="call_tool", params={"name": name, "args": dict(args or {}), **metadata})
        return self._execute(query, timeout_s=metadata.get("timeout_s"))
