from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore

from .fifo_scheduler import FIFOKernelScheduler
from .lanes import DEFAULT_SCHEDULER_LANES, SchedulerLaneSpec


class RoundRobinKernelScheduler(FIFOKernelScheduler):
    """RR shell for future LLM/context time slicing.

    Robot motion lanes remain non-preemptible; PR-08 wires generation context
    only for LLM work.
    """

    def __init__(
        self,
        queue_store: KernelQueueStore,
        managers: dict[str, object],
        lanes: tuple[SchedulerLaneSpec, ...] = DEFAULT_SCHEDULER_LANES,
        log_mode: str = "console",
        poll_timeout_s: float = 0.05,
        time_slice_s: float = 1.0,
    ) -> None:
        super().__init__(queue_store, managers, lanes=lanes, log_mode=log_mode, poll_timeout_s=poll_timeout_s)
        self.time_slice_s = time_slice_s

    def can_preempt_lane(self, queue_name: str) -> bool:
        if queue_name == KernelQueueName.ROBOT_MOTION:
            return False
        return any(lane.queue_name == queue_name and lane.preemptible for lane in self.lanes)
