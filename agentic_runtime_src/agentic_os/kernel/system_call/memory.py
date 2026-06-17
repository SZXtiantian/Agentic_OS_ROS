from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName

from .schema import MemoryQuery
from .syscall import BaseKernelSyscall


class MemorySyscall(BaseKernelSyscall):
    def __init__(self, agent_name: str, query: MemoryQuery) -> None:
        super().__init__(agent_name, query, target=KernelQueueName.MEMORY, queue_name=KernelQueueName.MEMORY)
