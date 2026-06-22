from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName

from .schema import ContextQuery
from .syscall import BaseKernelSyscall


class ContextSyscall(BaseKernelSyscall):
    def __init__(self, agent_name: str, query: ContextQuery) -> None:
        super().__init__(agent_name, query, target=KernelQueueName.CONTEXT, queue_name=KernelQueueName.CONTEXT)
