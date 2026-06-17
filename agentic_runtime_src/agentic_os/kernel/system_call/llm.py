from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName

from .schema import LLMQuery
from .syscall import BaseKernelSyscall


class LLMSyscall(BaseKernelSyscall):
    def __init__(self, agent_name: str, query: LLMQuery) -> None:
        super().__init__(agent_name, query, target=KernelQueueName.LLM, queue_name=KernelQueueName.LLM)
