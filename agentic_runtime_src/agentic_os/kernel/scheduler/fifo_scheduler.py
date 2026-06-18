from __future__ import annotations

from agentic_os.kernel.hooks import KernelEventSink, KernelQueueStore

from .base import BaseKernelScheduler
from .lanes import DEFAULT_SCHEDULER_LANES, SchedulerLaneSpec


class FIFOKernelScheduler(BaseKernelScheduler):
    def __init__(
        self,
        queue_store: KernelQueueStore,
        managers: dict[str, object],
        lanes: tuple[SchedulerLaneSpec, ...] = DEFAULT_SCHEDULER_LANES,
        log_mode: str = "console",
        poll_timeout_s: float = 0.05,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        super().__init__(queue_store, managers, lanes=lanes, log_mode=log_mode, poll_timeout_s=poll_timeout_s, event_sink=event_sink)
