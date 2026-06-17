from __future__ import annotations

from .llm import LLMSyscall
from .memory import MemorySyscall
from .models import KernelSyscall
from .robot import RobotCapabilitySyscall
from .schema import KernelQuery, LLMQuery, MemoryQuery, RobotCapabilityQuery, StorageQuery, ToolQuery
from .storage import StorageSyscall
from .tool import ToolSyscall


def create_syscall(agent_name: str, query: KernelQuery) -> KernelSyscall:
    if isinstance(query, LLMQuery):
        return LLMSyscall(agent_name, query)
    if isinstance(query, MemoryQuery):
        return MemorySyscall(agent_name, query)
    if isinstance(query, StorageQuery):
        return StorageSyscall(agent_name, query)
    if isinstance(query, ToolQuery):
        return ToolSyscall(agent_name, query)
    if isinstance(query, RobotCapabilityQuery):
        return RobotCapabilitySyscall(agent_name, query)
    raise TypeError(f"unsupported kernel query type: {type(query).__name__}")
