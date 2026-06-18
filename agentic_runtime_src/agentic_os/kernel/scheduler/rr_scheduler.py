from __future__ import annotations

from agentic_os.kernel.hooks import KernelEventSink, KernelQueueName, KernelQueueStore
from agentic_os.kernel.context import SimpleGenerationContextManager
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall

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
        generation_context: SimpleGenerationContextManager | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        super().__init__(queue_store, managers, lanes=lanes, log_mode=log_mode, poll_timeout_s=poll_timeout_s, event_sink=event_sink)
        self.time_slice_s = time_slice_s
        self.generation_context = generation_context or SimpleGenerationContextManager()

    def process_queue(self, lane: SchedulerLaneSpec) -> None:
        while self.active:
            syscall = self.queue_store.get(lane.queue_name, timeout_s=self.poll_timeout_s)
            if syscall is None:
                continue
            self._execute_syscall(lane, syscall)

    def can_preempt_lane(self, queue_name: str) -> bool:
        if queue_name == KernelQueueName.ROBOT_MOTION:
            return False
        return any(lane.queue_name == queue_name and lane.preemptible for lane in self.lanes)

    def _execute_syscall(self, lane: SchedulerLaneSpec, syscall: KernelSyscall) -> None:
        if lane.queue_name != KernelQueueName.LLM or not self.can_preempt_lane(lane.queue_name):
            super()._execute_syscall(lane, syscall)
            return

        manager_key = lane.manager_key or lane.queue_name
        manager = self.managers.get(manager_key) or self.managers.get(lane.queue_name)
        if manager is None:
            self._fail_syscall(syscall, "KERNEL_MANAGER_NOT_FOUND", f"manager not found for {manager_key}")
            return
        if not hasattr(manager, "complete_with_time_slice"):
            super()._execute_syscall(lane, syscall)
            return

        snapshot_id = str(syscall.params.get("generation_snapshot_id") or syscall.syscall_id)
        snapshot = self.generation_context.restore(snapshot_id)
        query = getattr(syscall, "query", None)
        try:
            syscall.mark_started()
            self._emit("syscall.started", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key)
            response, next_snapshot = manager.complete_with_time_slice(query, self.time_slice_s, snapshot)
        except TimeoutError as exc:
            self._fail_syscall(syscall, "KERNEL_MANAGER_TIMEOUT", str(exc))
            return
        except Exception as exc:
            self._fail_syscall(syscall, "KERNEL_MANAGER_FAILED", str(exc))
            return

        if next_snapshot is not None and next_snapshot.status == "suspended":
            syscall.mark_suspending()
            self._emit("syscall.suspended", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key)
            saved = self.generation_context.save(
                snapshot_id,
                syscall.syscall_id,
                getattr(query, "messages", []),
                next_snapshot.partial_text,
                metadata={**dict(next_snapshot.metadata), "response": response.to_dict()},
                agent_name=syscall.agent_name,
                model=next_snapshot.model or str(response.metadata.get("model", "")),
                status="suspended",
                tool_state=next_snapshot.tool_state,
                json_state=next_snapshot.json_state,
            )
            syscall.params["generation_snapshot_id"] = saved.generation_id
            syscall.params["partial_text"] = saved.partial_text
            syscall.mark_suspended()
            self.queue_store.add(lane.queue_name, syscall)
            return

        if response.success:
            if snapshot is not None:
                self.generation_context.save(
                    snapshot_id,
                    syscall.syscall_id,
                    getattr(query, "messages", []),
                    str(response.response_message.get("text", response.response_message))
                    if isinstance(response.response_message, dict)
                    else str(response.response_message or snapshot.partial_text),
                    metadata={**dict(snapshot.metadata), "response": response.to_dict()},
                    agent_name=syscall.agent_name,
                    model=snapshot.model or str(response.metadata.get("model", "")),
                    status="done",
                    tool_state=snapshot.tool_state,
                    json_state=snapshot.json_state,
                )
            syscall.finish(response=response)
            self._emit("syscall.done", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key)
        else:
            syscall.fail(response.error_code or "KERNEL_MANAGER_REJECTED", response)
            self._emit("syscall.failed", syscall=syscall, queue_name=lane.queue_name, manager_key=manager_key, error_code=syscall.error_code)
