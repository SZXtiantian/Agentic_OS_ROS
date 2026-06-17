from __future__ import annotations

from dataclasses import dataclass

from agentic_os.kernel.hooks import KernelQueueName


@dataclass(frozen=True)
class SchedulerLaneSpec:
    name: str
    queue_name: str
    concurrent: bool
    max_workers: int = 1
    preemptible: bool = False
    manager_key: str = ""


DEFAULT_SCHEDULER_LANES = (
    SchedulerLaneSpec("llm", KernelQueueName.LLM, concurrent=True, max_workers=1, preemptible=True, manager_key="llm"),
    SchedulerLaneSpec("memory", KernelQueueName.MEMORY, concurrent=True, max_workers=1, manager_key="memory"),
    SchedulerLaneSpec("storage", KernelQueueName.STORAGE, concurrent=True, max_workers=1, manager_key="storage"),
    SchedulerLaneSpec("tool", KernelQueueName.TOOL, concurrent=True, max_workers=1, manager_key="tool"),
    SchedulerLaneSpec(
        "robot_motion",
        KernelQueueName.ROBOT_MOTION,
        concurrent=False,
        max_workers=1,
        preemptible=False,
        manager_key="robot_motion",
    ),
    SchedulerLaneSpec(
        "robot_sensor",
        KernelQueueName.ROBOT_SENSOR,
        concurrent=True,
        max_workers=1,
        manager_key="robot_sensor",
    ),
    SchedulerLaneSpec("human", KernelQueueName.HUMAN, concurrent=True, max_workers=1, manager_key="human"),
)
