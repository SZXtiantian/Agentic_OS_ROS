from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName

from .schema import ToolQuery
from .syscall import BaseKernelSyscall


class ToolSyscall(BaseKernelSyscall):
    def __init__(self, agent_name: str, query: ToolQuery) -> None:
        super().__init__(agent_name, query, target=KernelQueueName.TOOL, queue_name=KernelQueueName.TOOL)
