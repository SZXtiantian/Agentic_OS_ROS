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
    batchable: bool = False
    batch_window_ms: int = 0
    max_batch_size: int = 1
    queue_timeout_s: float | None = None


DEFAULT_SCHEDULER_LANES = (
    SchedulerLaneSpec(
        "llm",
        KernelQueueName.LLM,
        concurrent=True,
        max_workers=1,
        preemptible=True,
        manager_key="llm",
        batchable=True,
        batch_window_ms=20,
        max_batch_size=8,
    ),
    SchedulerLaneSpec("memory", KernelQueueName.MEMORY, concurrent=True, max_workers=1, manager_key="memory"),
    SchedulerLaneSpec("storage", KernelQueueName.STORAGE, concurrent=True, max_workers=1, manager_key="storage"),
    SchedulerLaneSpec("tool", KernelQueueName.TOOL, concurrent=True, max_workers=1, manager_key="tool"),
    SchedulerLaneSpec("context", KernelQueueName.CONTEXT, concurrent=True, max_workers=1, manager_key="context"),
    SchedulerLaneSpec("skill", KernelQueueName.SKILL, concurrent=True, max_workers=1, manager_key="skill"),
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


DEFAULT_DAG_DISPATCH_LANES = {
    "emergency": KernelQueueName.ROBOT_MOTION,
    "safety": KernelQueueName.ROBOT_SENSOR,
    "motion": KernelQueueName.ROBOT_MOTION,
    "perception": KernelQueueName.ROBOT_SENSOR,
    "llm_tool": KernelQueueName.LLM,
    "io_audit": KernelQueueName.STORAGE,
    "background": KernelQueueName.CONTEXT,
}
