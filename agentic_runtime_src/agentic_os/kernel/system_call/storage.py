from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName

from .schema import StorageQuery
from .syscall import BaseKernelSyscall


class StorageSyscall(BaseKernelSyscall):
    def __init__(self, agent_name: str, query: StorageQuery) -> None:
        super().__init__(agent_name, query, target=KernelQueueName.STORAGE, queue_name=KernelQueueName.STORAGE)
