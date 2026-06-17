"""System call primitives ported from AIOS for AgenticOS."""

from .executor import SyscallExecutionResult, SyscallExecutor
from .factory import create_syscall
from .llm import LLMSyscall
from .memory import MemorySyscall
from .models import KernelSyscall, KernelSyscallStatus
from .protocol import KernelRequestHandler
from .robot import RobotCapabilitySyscall, SkillSyscall
from .schema import (
    KernelQuery,
    KernelResponse,
    LLMQuery,
    MemoryQuery,
    RobotCapabilityQuery,
    StorageQuery,
    ToolQuery,
)
from .storage import StorageSyscall
from .tool import ToolSyscall

__all__ = [
    "KernelSyscall",
    "KernelSyscallStatus",
    "KernelQuery",
    "KernelResponse",
    "KernelRequestHandler",
    "LLMQuery",
    "LLMSyscall",
    "MemoryQuery",
    "MemorySyscall",
    "RobotCapabilityQuery",
    "RobotCapabilitySyscall",
    "SkillSyscall",
    "StorageQuery",
    "StorageSyscall",
    "SyscallExecutionResult",
    "SyscallExecutor",
    "ToolQuery",
    "ToolSyscall",
    "create_syscall",
]
