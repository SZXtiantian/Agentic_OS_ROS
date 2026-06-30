from __future__ import annotations

from typing import Any

from .audit import SchedulerAudit
from .graph_store import TaskGraphStore
from .models import TaskGraphStatus, TaskNodeStatus
from .ready_queue import ReadyQueue
from .resource_arbiter import ResourceArbiter


class SchedulerLifecycleHooks:
    def __init__(
        self,
        *,
        graph_store: TaskGraphStore,
        ready_queue: ReadyQueue,
        resource_arbiter: ResourceArbiter,
        audit: SchedulerAudit,
        preemption_manager=None,
        queue_store=None,
    ) -> None:
        self.graph_store = graph_store
        self.ready_queue = ready_queue
        self.resource_arbiter = resource_arbiter
        self.audit = audit
        self.preemption_manager = preemption_manager
        self.queue_store = queue_store
        self._held_syscalls_by_agent: dict[str, list[Any]] = {}

    def on_suspended(self, agent_id: str, *, reason: str = "", held_syscall_ids: list[str] | None = None) -> None:
        touched_graph_ids: set[str] = set()
        held_ids = list(held_syscall_ids or [])
        if not held_ids:
            held = self._hold_queued_syscalls(agent_id, reason=reason)
            held_ids = [syscall.syscall_id for syscall in held]
        for node in self.graph_store.nodes_for_agent(agent_id):
            if node.status == TaskNodeStatus.READY:
                self.ready_queue.remove(node.node_id)
                self.graph_store.mark_status(node.node_id, TaskNodeStatus.SUSPENDED)
                touched_graph_ids.add(node.task_graph_id)
            elif node.status == TaskNodeStatus.RUNNING:
                self._handle_running_suspend(node, reason=reason)
                touched_graph_ids.add(node.task_graph_id)
        self._mark_graphs_partially_suspended(touched_graph_ids)
        self.audit.emit("scheduler.agent.suspended", agent_id=agent_id, reason=reason, held_syscall_ids=held_ids)

    def on_resumed(self, agent_id: str, *, reason: str = "", resumed_syscall_ids: list[str] | None = None) -> None:
        touched_graph_ids: set[str] = set()
        resumed_ids = list(resumed_syscall_ids or [])
        if not resumed_ids:
            resumed_ids = self._resume_held_syscalls(agent_id, reason=reason)
        for node in self.graph_store.nodes_for_agent(agent_id):
            if node.status == TaskNodeStatus.SUSPENDED:
                self.graph_store.mark_status(node.node_id, TaskNodeStatus.WAITING)
                touched_graph_ids.add(node.task_graph_id)
        self._restore_partially_suspended_graphs(touched_graph_ids)
        self.audit.emit("scheduler.agent.resumed", agent_id=agent_id, reason=reason, resumed_syscall_ids=resumed_ids)

    def on_terminal(self, agent_id: str, *, event_type: str, reason: str = "", cancelled_syscall_ids: list[str] | None = None) -> None:
        touched_graph_ids: set[str] = set()
        cancelled_ids = list(cancelled_syscall_ids or [])
        cancelled_ids.extend(self._cancel_queued_and_held_syscalls(agent_id, reason=reason or event_type))
        terminal_status, error_code, node_event_type = _terminal_node_outcome(event_type)
        for node in self.graph_store.nodes_for_agent(agent_id):
            if node.status not in TaskNodeStatus.TERMINAL:
                self.ready_queue.remove(node.node_id)
                self.graph_store.mark_status(node.node_id, terminal_status, error_code=error_code)
                touched_graph_ids.add(node.task_graph_id)
                self.audit.emit(
                    node_event_type,
                    success=False,
                    error_code=error_code,
                    agent_id=node.agent_id,
                    app_id=node.app_id,
                    session_id=node.session_id,
                    task_graph_id=node.task_graph_id,
                    node_id=node.node_id,
                    lifecycle_event=event_type,
                    reason=reason,
                )
        release_result = self.resource_arbiter.release_by_agent(agent_id, reason=event_type)
        if not release_result.success:
            touched_graph_ids.update(self._mark_release_failure(agent_id, release_result, event_type=event_type, reason=reason))
        self._mark_terminal_graphs(touched_graph_ids, event_type, release_failed=not release_result.success)
        self.audit.emit(f"scheduler.agent.{event_type}", agent_id=agent_id, reason=reason, cancelled_syscall_ids=sorted(set(cancelled_ids)))

    def _hold_queued_syscalls(self, agent_id: str, *, reason: str) -> list[Any]:
        if self.queue_store is None or not hasattr(self.queue_store, "hold_by_agent"):
            return []
        held = list(self.queue_store.hold_by_agent(agent_id, reason=reason))
        if held:
            self._held_syscalls_by_agent.setdefault(agent_id, []).extend(held)
            self.audit.emit(
                "scheduler.agent.syscalls_held",
                agent_id=agent_id,
                reason=reason,
                syscall_ids=[syscall.syscall_id for syscall in held],
            )
        return held

    def _resume_held_syscalls(self, agent_id: str, *, reason: str) -> list[str]:
        held = self._held_syscalls_by_agent.pop(agent_id, [])
        if not held or self.queue_store is None or not hasattr(self.queue_store, "requeue_many"):
            return []
        resumed = list(self.queue_store.requeue_many(held, reason=reason))
        if resumed:
            self.audit.emit(
                "scheduler.agent.syscalls_resumed",
                agent_id=agent_id,
                reason=reason,
                syscall_ids=resumed,
            )
        return resumed

    def _cancel_queued_and_held_syscalls(self, agent_id: str, *, reason: str) -> list[str]:
        cancelled_ids: list[str] = []
        if self.queue_store is not None and hasattr(self.queue_store, "cancel_by_agent"):
            cancelled = list(self.queue_store.cancel_by_agent(agent_id, reason=reason))
            cancelled_ids.extend(syscall.syscall_id for syscall in cancelled)
        for syscall in self._held_syscalls_by_agent.pop(agent_id, []):
            syscall.cancel(reason)
            syscall.event.set()
            cancelled_ids.append(syscall.syscall_id)
        if cancelled_ids:
            self.audit.emit(
                "scheduler.agent.syscalls_cancelled",
                agent_id=agent_id,
                reason=reason,
                syscall_ids=sorted(set(cancelled_ids)),
            )
        return cancelled_ids

    def _handle_running_suspend(self, node, *, reason: str) -> None:
        if self.preemption_manager is None:
            self.audit.emit(
                "scheduler.preemption.rejected",
                success=False,
                error_code="SCHEDULER_PREEMPTION_UNSUPPORTED",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                syscall_id=node.syscall_id,
                goal_id=node.user_goal_id,
                reason=reason,
            )
            return
        result = self.preemption_manager.request_preemption(node, reason=reason)
        if result.success:
            release_result = self.resource_arbiter.release(list(node.resource_lease_ids), reason="agent_suspended")
            if not release_result.success:
                self.graph_store.mark_status(node.node_id, TaskNodeStatus.BLOCKED, error_code=release_result.error_code)
                self.audit.emit(
                    "scheduler.node.blocked",
                    success=False,
                    error_code=release_result.error_code,
                    agent_id=node.agent_id,
                    app_id=node.app_id,
                    session_id=node.session_id,
                    task_graph_id=node.task_graph_id,
                    node_id=node.node_id,
                    syscall_id=node.syscall_id,
                    goal_id=node.user_goal_id,
                    reason="agent_suspended_release_failed",
                    **dict(release_result.metadata),
                )
                return
            node.resource_lease_ids = []
            self.graph_store.mark_status(node.node_id, TaskNodeStatus.SUSPENDED)
        else:
            self.graph_store.mark_status(node.node_id, TaskNodeStatus.BLOCKED, error_code=result.error_code)
            self.audit.emit(
                "scheduler.node.blocked",
                success=False,
                error_code=result.error_code,
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                syscall_id=node.syscall_id,
                goal_id=node.user_goal_id,
                reason=reason,
            )

    def _mark_graphs_partially_suspended(self, graph_ids: set[str]) -> None:
        changed = False
        for graph_id in graph_ids:
            graph = self.graph_store.global_dag.graphs.get(graph_id)
            if graph is not None and graph.status not in {
                TaskGraphStatus.COMPLETED,
                TaskGraphStatus.FAILED,
                TaskGraphStatus.CANCELLED,
                TaskGraphStatus.REJECTED,
            }:
                graph.status = TaskGraphStatus.PARTIALLY_SUSPENDED
                changed = True
        if changed:
            self.graph_store.apply_changed_nodes([])

    def _restore_partially_suspended_graphs(self, graph_ids: set[str]) -> None:
        changed = False
        for graph_id in graph_ids:
            graph = self.graph_store.global_dag.graphs.get(graph_id)
            if graph is not None and graph.status == TaskGraphStatus.PARTIALLY_SUSPENDED:
                graph.status = TaskGraphStatus.ADMITTED
                changed = True
        if changed:
            self.graph_store.apply_changed_nodes([])

    def _mark_release_failure(self, agent_id: str, release_result, *, event_type: str, reason: str) -> set[str]:
        touched_graph_ids: set[str] = set()
        holder_node_id = str(release_result.metadata.get("holder_node_id") or "")
        active_leases = [
            lease
            for lease in self.resource_arbiter.snapshot().get("leases", {}).values()
            if lease.get("holder_agent_id") == agent_id
        ]
        holder_node_ids = {holder_node_id} if holder_node_id else set()
        holder_node_ids.update(str(lease.get("holder_node_id") or "") for lease in active_leases)
        for node_id in sorted(node_id for node_id in holder_node_ids if node_id):
            try:
                node = self.graph_store.get_node(node_id)
            except KeyError:
                continue
            self.graph_store.mark_status(node.node_id, TaskNodeStatus.FAILED, error_code=release_result.error_code)
            touched_graph_ids.add(node.task_graph_id)
            self.audit.emit(
                "scheduler.node.failed",
                success=False,
                error_code=release_result.error_code,
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                lifecycle_event=event_type,
                reason=reason,
                **dict(release_result.metadata),
            )
        self.audit.emit(
            "scheduler.agent.resource_release_failed",
            success=False,
            error_code=release_result.error_code,
            agent_id=agent_id,
            lifecycle_event=event_type,
            reason=reason,
            **dict(release_result.metadata),
        )
        return touched_graph_ids

    def _mark_terminal_graphs(self, graph_ids: set[str], event_type: str, *, release_failed: bool = False) -> None:
        changed = False
        graph_status = TaskGraphStatus.FAILED if release_failed else _terminal_graph_status(event_type)
        for graph_id in graph_ids:
            graph = self.graph_store.global_dag.graphs.get(graph_id)
            if graph is not None and graph.status != TaskGraphStatus.COMPLETED:
                graph.status = graph_status
                changed = True
        if changed:
            self.graph_store.apply_changed_nodes([])


def _terminal_node_outcome(event_type: str) -> tuple[str, str, str]:
    if event_type in {"crashed", "failed"}:
        return TaskNodeStatus.FAILED, f"SCHEDULER_AGENT_{event_type.upper()}", "scheduler.node.failed"
    if event_type == "reaped":
        return TaskNodeStatus.STALE, "SCHEDULER_AGENT_REAPED", "scheduler.node.stale"
    return TaskNodeStatus.CANCELLED, f"SCHEDULER_AGENT_{event_type.upper()}", "scheduler.node.cancelled"


def _terminal_graph_status(event_type: str) -> str:
    if event_type in {"crashed", "failed", "reaped"}:
        return TaskGraphStatus.FAILED
    return TaskGraphStatus.CANCELLED
