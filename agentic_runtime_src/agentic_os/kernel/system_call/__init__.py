"""System call primitives ported from AIOS for AgenticOS."""

from .executor import SyscallExecutionResult, SyscallExecutor
from .models import KernelSyscall, KernelSyscallStatus

__all__ = [
    "KernelSyscall",
    "KernelSyscallStatus",
    "SyscallExecutionResult",
    "SyscallExecutor",
]

