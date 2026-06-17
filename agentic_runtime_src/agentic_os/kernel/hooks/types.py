from __future__ import annotations

from typing import Protocol

from agentic_os.kernel.system_call.models import KernelSyscall


class KernelQueueName:
    LLM = "llm"
    MEMORY = "memory"
    STORAGE = "storage"
    TOOL = "tool"
    ROBOT_MOTION = "robot_motion"
    ROBOT_SENSOR = "robot_sensor"
    HUMAN = "human"


DEFAULT_KERNEL_QUEUES = (
    KernelQueueName.LLM,
    KernelQueueName.MEMORY,
    KernelQueueName.STORAGE,
    KernelQueueName.TOOL,
    KernelQueueName.ROBOT_MOTION,
    KernelQueueName.ROBOT_SENSOR,
    KernelQueueName.HUMAN,
)


class KernelQueueAddMessage(Protocol):
    def __call__(self, queue_name: str, syscall: KernelSyscall) -> None:
        ...


class KernelQueueGetMessage(Protocol):
    def __call__(self, queue_name: str, timeout_s: float | None = None) -> KernelSyscall | None:
        ...
