from __future__ import annotations

from .context import ContextSyscall
from .llm import LLMSyscall
from .memory import MemorySyscall
from .models import KernelSyscall
from .robot import RobotCapabilitySyscall
from .schema import ContextQuery, KernelQuery, LLMQuery, MemoryQuery, RobotCapabilityQuery, SkillQuery, StorageQuery, ToolQuery
from .skill import SkillSyscall
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
    if isinstance(query, ContextQuery):
        return ContextSyscall(agent_name, query)
    if isinstance(query, SkillQuery):
        return SkillSyscall(agent_name, query)
    if isinstance(query, RobotCapabilityQuery):
        return RobotCapabilitySyscall(agent_name, query)
    raise TypeError(f"unsupported kernel query type: {type(query).__name__}")
