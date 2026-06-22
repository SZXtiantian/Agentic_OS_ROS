"""System call primitives ported from AIOS for AgenticOS."""

from .executor import SyscallExecutionResult, SyscallExecutor
from .factory import create_syscall
from .context import ContextSyscall
from .llm import LLMSyscall
from .memory import MemorySyscall
from .models import KernelSyscall, KernelSyscallStatus
from .protocol import KernelRequestHandler
from .robot import RobotCapabilitySyscall
from .schema import (
    ContextQuery,
    KernelQuery,
    KernelResponse,
    LLMQuery,
    MemoryQuery,
    RobotCapabilityQuery,
    SkillQuery,
    StorageQuery,
    ToolQuery,
)
from .skill import SkillSyscall
from .storage import StorageSyscall
from .tool import ToolSyscall

__all__ = [
    "KernelSyscall",
    "KernelSyscallStatus",
    "KernelQuery",
    "KernelResponse",
    "KernelRequestHandler",
    "ContextQuery",
    "ContextSyscall",
    "LLMQuery",
    "LLMSyscall",
    "MemoryQuery",
    "MemorySyscall",
    "RobotCapabilityQuery",
    "RobotCapabilitySyscall",
    "SkillQuery",
    "SkillSyscall",
    "StorageQuery",
    "StorageSyscall",
    "SyscallExecutionResult",
    "SyscallExecutor",
    "ToolQuery",
    "ToolSyscall",
    "create_syscall",
]
