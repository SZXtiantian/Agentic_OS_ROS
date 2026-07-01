from __future__ import annotations

from typing import Any

from agentic_os.kernel.hooks import KernelEventSink, KernelQueueStore
from agentic_os.kernel.system_call import KernelResponse
from agentic_os.kernel.system_call.models import monotonic_id

from .admission import AdmissionController
from .audit import SchedulerAudit
from .debug import SchedulerDebugExporter
from .dispatch import CapabilityDispatchAdapter, DispatchLaneMapper
from .environment import EnvironmentFact, EnvironmentStore
from .errors import SchedulerError
from .fifo_scheduler import FIFOKernelScheduler
from .fusion import GoalFusionEngine
from .graph_store import TaskGraphStore
from .lifecycle_integration import SchedulerLifecycleHooks
from .models import QueryType, TaskNodeStatus, now_ns, stable_hash_payload
from .opportunity import OpportunityIndex
from .preconditions import PreconditionEvaluator
from .preemption import PreemptionManager
from .priority import PriorityScorer
from .ready_queue import ReadyQueue
from .reconstruction import DynamicGraphEvent, OnlineGraphReconstructor
from .resource_arbiter import ResourceArbiter
from .resources import ResourceLease
from .task_graph import TaskGraph
from .task_graph_planner import TaskGraphPlanner
from .task_node import TaskNode


class EnvironmentAwareDAGScheduler(FIFOKernelScheduler):
    def __init__(
        self,
        queue_store: KernelQueueStore,
        managers: dict[str, object],
        *,
        kernel_service: Any | None = None,
        policy: str = "env_aware_priority_dag",
        event_sink: KernelEventSink | None = None,
        agent_lifecycle=None,
        audit_logger=None,
        capability_registry: Any | None = None,
        device_arbiter: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(queue_store, managers, event_sink=event_sink, agent_lifecycle=agent_lifecycle, **kwargs)
        self.kernel_service = kernel_service
        self.policy = policy
        self.audit = SchedulerAudit(event_sink=event_sink, audit_logger=audit_logger)
        self.graph_store = TaskGraphStore()
        self.environment_store = EnvironmentStore()
        self.ready_queue = ReadyQueue()
        self.priority_scorer = PriorityScorer(agent_lifecycle)
        self.precondition_evaluator = PreconditionEvaluator(self.environment_store)
        self.resource_arbiter = ResourceArbiter(
            agent_lifecycle=agent_lifecycle,
            graph_store=self.graph_store,
            audit=self.audit,
            device_arbiter=device_arbiter,
        )
        self.lane_mapper = DispatchLaneMapper()
        self.dispatch_adapter = CapabilityDispatchAdapter(kernel_service=kernel_service, lane_mapper=self.lane_mapper, audit=self.audit) if kernel_service is not None else None
        self.admission = AdmissionController(capability_registry=capability_registry)
        self.opportunity_index = OpportunityIndex()
        self.fusion_engine = GoalFusionEngine(audit=self.audit, kernel_service=kernel_service)
        self.preemption = PreemptionManager(kernel_service=kernel_service, audit=self.audit)
        self.lifecycle_hooks = SchedulerLifecycleHooks(
            graph_store=self.graph_store,
            ready_queue=self.ready_queue,
            resource_arbiter=self.resource_arbiter,
            audit=self.audit,
            preemption_manager=self.preemption,
            queue_store=queue_store,
        )
        self.debug_exporter = SchedulerDebugExporter()
        self.reconstructor = OnlineGraphReconstructor(audit=self.audit)
        self.planner = TaskGraphPlanner(kernel_service=kernel_service, admission=self.admission, audit=self.audit) if kernel_service is not None else None

    def status(self) -> dict[str, Any]:
        base = super().status()
        counts = self.graph_store.global_dag.counts()
        resource_snapshot = self.resource_arbiter.snapshot()
        fact_snapshot = self.environment_store.snapshot()
        base.update(
            {
                "policy": self.policy,
                "global_revision": self.graph_store.revision,
                "graph_revision": self.graph_store.revision,
                "ready": counts.get(TaskNodeStatus.READY, 0),
                "running": counts.get(TaskNodeStatus.RUNNING, 0),
                "blocked": counts.get(TaskNodeStatus.BLOCKED, 0),
                "completed": counts.get(TaskNodeStatus.COMPLETED, 0),
                "failed": counts.get(TaskNodeStatus.FAILED, 0),
                "lane_capacity": {lane.name: lane.max_workers for lane in self.lanes},
                "lease_count": len(resource_snapshot["leases"]),
                "fact_count": len(fact_snapshot["facts"]),
            }
        )
        return base

    def submit_goal(self, goal: str, *, agent_id: str, app_id: str, session_id: str, agent_name: str = "") -> KernelResponse:
        goal_id = monotonic_id("goal")
        self.audit.emit(
            "scheduler.goal.submitted",
            agent_id=agent_id,
            app_id=app_id,
            session_id=session_id,
            goal_id=goal_id,
            success=True,
        )
        if self.planner is None:
            return KernelResponse.error(
                "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE",
                metadata={"reason": "kernel service not configured", "goal_id": goal_id},
            )
        try:
            graph = self.planner.generate_task_graph(
                goal,
                agent_id=agent_id,
                app_id=app_id,
                session_id=session_id,
                agent_name=agent_name,
                user_goal_id=goal_id,
            )
        except SchedulerError as exc:
            return KernelResponse.error(exc.error_code, metadata={"goal_id": goal_id, **exc.metadata})
        return self.submit_graph(graph)

    def submit_graph(self, graph: TaskGraph) -> KernelResponse:
        result = self.admission.admit(graph)
        if not result.success:
            self.audit.emit(
                "scheduler.graph.rejected",
                success=False,
                error_code=result.error_code,
                task_graph_id=graph.task_graph_id,
                agent_id=graph.agent_id,
                app_id=graph.app_id,
                session_id=graph.session_id,
            )
            return KernelResponse.error(result.error_code, metadata=result.metadata)
        plan = self.fusion_engine.find_opportunities(
            global_dag=self.graph_store.global_dag,
            incoming_graph=graph,
            environment=self.environment_store,
            opportunity_index=self.opportunity_index,
        )
        admitted_graph = graph
        if plan.accepted:
            if self.kernel_service is not None:
                reasoning_result = self.fusion_engine.explain_plan_with_real_llm(
                    plan,
                    incoming_graph=graph,
                    global_dag=self.graph_store.global_dag,
                    agent_name=graph.app_id,
                )
                if not reasoning_result.success:
                    self.audit.emit(
                        "scheduler.graph.rejected",
                        success=False,
                        error_code=reasoning_result.error_code,
                        task_graph_id=graph.task_graph_id,
                        agent_id=graph.agent_id,
                        app_id=graph.app_id,
                        session_id=graph.session_id,
                        fusion_plan_id=plan.fusion_plan_id,
                        upstream_error_code=reasoning_result.metadata.get("upstream_error_code", ""),
                    )
                    return KernelResponse.error(
                        reasoning_result.error_code,
                        metadata={
                            "task_graph_id": graph.task_graph_id,
                            "fusion_plan_id": plan.fusion_plan_id,
                            "fusion_plan": plan.to_dict(),
                            **reasoning_result.metadata,
                        },
                    )
            commit = self.fusion_engine.commit_fusion(self.graph_store, graph, plan)
            if not commit.success:
                self.audit.emit(
                    "scheduler.graph.rejected",
                    success=False,
                    error_code=commit.error_code,
                    task_graph_id=graph.task_graph_id,
                    agent_id=graph.agent_id,
                    app_id=graph.app_id,
                    session_id=graph.session_id,
                    fusion_plan_id=plan.fusion_plan_id,
                    retry_required=commit.retry_required,
                    **dict(commit.metadata),
                )
                return KernelResponse.error(commit.error_code, metadata=commit.to_dict())
            admitted_graph = self.graph_store.get_graph(graph.task_graph_id)
        else:
            self.graph_store.add_graph(graph)
        self.opportunity_index.rebuild_from_graph(admitted_graph)
        self.audit.emit(
            "scheduler.graph.admitted",
            task_graph_id=graph.task_graph_id,
            agent_id=graph.agent_id,
            app_id=graph.app_id,
            session_id=graph.session_id,
            success=True,
        )
        self.refresh_ready_nodes()
        return KernelResponse.ok({"task_graph_id": graph.task_graph_id, "fusion_plan": plan.to_dict()}, data={"task_graph_id": graph.task_graph_id})

    def refresh_ready_nodes(self) -> None:
        timestamp = now_ns()
        for node_id in sorted(self.graph_store.global_dag.ready_set):
            node = self.graph_store.get_node(node_id)
            if self.graph_store.dependencies_completed(node):
                continue
            self.ready_queue.remove(node.node_id)
            self.graph_store.mark_status(node.node_id, TaskNodeStatus.WAITING)
        for node in self.graph_store.waiting_nodes():
            if not self.graph_store.dependencies_completed(node):
                self.graph_store.mark_status(node.node_id, TaskNodeStatus.WAITING)
                continue
            dispatchable = self._node_still_dispatchable(node, timestamp)
            if not dispatchable.success:
                self._block_node(node, dispatchable.error_code, metadata=dispatchable.metadata)
                continue
            node.lane = self.lane_mapper.derive_lane(node)
            self.graph_store.mark_status(node.node_id, TaskNodeStatus.READY)
            key = self.priority_scorer.score(node, timestamp)
            self.ready_queue.push(node.node_id, key)
            self.audit.emit(
                "scheduler.priority.computed",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                priority=key.__dict__,
            )
            self.audit.emit(
                "scheduler.node.ready",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
            )

    def recompute_dynamic_priorities(self, timestamp: int | None = None) -> None:
        at_ns = timestamp if timestamp is not None else now_ns()
        for node_id in sorted(self.graph_store.global_dag.ready_set):
            try:
                node = self.graph_store.get_node(node_id)
            except KeyError:
                continue
            if node.status != TaskNodeStatus.READY:
                continue
            node.lane = self.lane_mapper.derive_lane(node)
            key = self.priority_scorer.score(node, at_ns)
            self.ready_queue.push(node.node_id, key)
            self.audit.emit(
                "scheduler.priority.computed",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                priority=key.__dict__,
                reason="dynamic_recompute",
            )

    def tick(self, *, max_dispatch: int = 1) -> list[dict[str, Any]]:
        timestamp = now_ns()
        for fact in self.environment_store.expire(timestamp):
            self.audit.emit("scheduler.environment.fact_expired", fact_id=fact.fact_id, fact_key=fact.key)
            self._apply_environment_fact_event("environment_fact_expired", fact)
        expired_leases = self.resource_arbiter.expire(timestamp)
        for lease in expired_leases:
            cleanup_error_code = str(lease.metadata.get("expiration_error_code") or "")
            error_code = cleanup_error_code or "SCHEDULER_RESOURCE_LEASE_EXPIRED"
            status = TaskNodeStatus.FAILED if cleanup_error_code else TaskNodeStatus.STALE
            event_type = "scheduler.node.failed" if cleanup_error_code else "scheduler.node.stale"
            try:
                self.graph_store.mark_status(lease.holder_node_id, status, error_code=error_code)
                self.audit.emit(
                    event_type,
                    success=False,
                    error_code=error_code,
                    agent_id=lease.holder_agent_id,
                    node_id=lease.holder_node_id,
                    resource_lease_id=lease.lease_id,
                    resource_id=lease.resource_id,
                    lease_status=lease.status,
                    cleanup_error_code=cleanup_error_code,
                )
            except KeyError:
                pass
        self.refresh_ready_nodes()
        self.recompute_dynamic_priorities(timestamp)
        decisions: list[dict[str, Any]] = []
        deferred_for_capacity: list[TaskNode] = []
        for _ in range(max_dispatch):
            node_id = self.ready_queue.pop_best()
            if node_id is None:
                break
            node = self.graph_store.get_node(node_id)
            if node.status != TaskNodeStatus.READY:
                continue
            if not self.graph_store.dependencies_completed(node):
                self.graph_store.mark_status(node.node_id, TaskNodeStatus.WAITING)
                continue
            dispatchable = self._node_still_dispatchable(node, timestamp)
            if not dispatchable.success:
                self._block_node(node, dispatchable.error_code, metadata=dispatchable.metadata)
                continue
            if not self._lane_has_capacity(node):
                self._defer_for_lane_capacity(node)
                deferred_for_capacity.append(node)
                continue
            decision = self._dispatch_node(node)
            decisions.append(decision)
        self._requeue_deferred_nodes(deferred_for_capacity, timestamp)
        return decisions

    def apply_dynamic_graph_event(self, event: DynamicGraphEvent | dict[str, Any], *, task_graph_id: str | None = None) -> KernelResponse:
        try:
            dynamic_event = _coerce_dynamic_event(event)
        except (TypeError, ValueError) as exc:
            self.audit.emit(
                "scheduler.reconstruction.rejected",
                success=False,
                error_code="SCHEDULER_DYNAMIC_EVENT_INVALID",
                reason=str(exc),
            )
            return KernelResponse.error("SCHEDULER_DYNAMIC_EVENT_INVALID", metadata={"reason": str(exc)})
        if not dynamic_event.event_type:
            self.audit.emit(
                "scheduler.reconstruction.rejected",
                success=False,
                error_code="SCHEDULER_DYNAMIC_EVENT_INVALID",
                dynamic_event_id=dynamic_event.event_id,
                reason="event_type required",
            )
            return KernelResponse.error("SCHEDULER_DYNAMIC_EVENT_INVALID", metadata={"dynamic_event_id": dynamic_event.event_id, "reason": "event_type required"})

        graph_ids = [task_graph_id] if task_graph_id else sorted(self.graph_store.global_dag.graphs)
        if task_graph_id and task_graph_id not in self.graph_store.global_dag.graphs:
            self.audit.emit(
                "scheduler.reconstruction.rejected",
                success=False,
                error_code="SCHEDULER_GRAPH_NOT_FOUND",
                task_graph_id=task_graph_id,
                dynamic_event_id=dynamic_event.event_id,
                dynamic_event_type=dynamic_event.event_type,
            )
            return KernelResponse.error("SCHEDULER_GRAPH_NOT_FOUND", metadata={"task_graph_id": task_graph_id, "dynamic_event_id": dynamic_event.event_id})

        results: list[dict[str, Any]] = []
        committed_graphs: list[str] = []
        for graph_id in graph_ids:
            graph = self.graph_store.get_graph(graph_id)
            staged = self.reconstructor.stage_graph_mutation(
                graph,
                dynamic_event,
                base_revision=self.graph_store.revision,
                environment=self.environment_store,
            )
            if not staged.success:
                result = staged.to_dict()
                self.reconstructor.commit_staged_mutation(self.graph_store, staged)
                results.append(result)
                continue
            if not staged.impacted_nodes:
                results.append(
                    {
                        "success": True,
                        "task_graph_id": graph_id,
                        "dynamic_event_id": dynamic_event.event_id,
                        "dynamic_event_type": dynamic_event.event_type,
                        "committed": False,
                        "impacted_nodes": [],
                        "reusable_fact_keys": list(staged.reusable_fact_keys),
                    }
                )
                continue
            result = self.reconstructor.commit_staged_mutation(self.graph_store, staged)
            results.append(result)
            if result.get("success"):
                committed_graphs.append(graph_id)

        if committed_graphs:
            timestamp = now_ns()
            for graph_id in committed_graphs:
                self.opportunity_index.rebuild_from_graph(self.graph_store.get_graph(graph_id))
            self.refresh_ready_nodes()
            self._block_impacted_ready_nodes(results, timestamp)
            self.recompute_dynamic_priorities(timestamp)
            payload = {
                "dynamic_event_id": dynamic_event.event_id,
                "dynamic_event_type": dynamic_event.event_type,
                "committed_graphs": committed_graphs,
                "results": results,
            }
            return KernelResponse.ok(payload, data=payload)

        failed = [result for result in results if not result.get("success", False)]
        if failed:
            error_code = str(failed[0].get("error_code") or "SCHEDULER_DYNAMIC_GRAPH_EVENT_FAILED")
            return KernelResponse.error(error_code, metadata={"dynamic_event_id": dynamic_event.event_id, "results": results})
        payload = {
            "dynamic_event_id": dynamic_event.event_id,
            "dynamic_event_type": dynamic_event.event_type,
            "committed_graphs": [],
            "results": results,
        }
        return KernelResponse.ok(payload, data=payload)

    def _apply_environment_fact_event(self, event_type: str, fact: EnvironmentFact) -> KernelResponse:
        return self.apply_dynamic_graph_event(
            DynamicGraphEvent.create(
                event_type,
                fact_key=fact.key,
                metadata={
                    "fact_id": fact.fact_id,
                    "source_node_id": fact.source_node_id,
                    "source_syscall_id": fact.source_syscall_id,
                    "source_audit_id": fact.source_audit_id,
                    "world_epoch": fact.world_epoch,
                },
            )
        )

    def _block_impacted_ready_nodes(self, results: list[dict[str, Any]], timestamp: int) -> None:
        impacted_node_ids: set[str] = set()
        for result in results:
            impacted_node_ids.update(str(node_id) for node_id in result.get("dirty_nodes_refreshed", []) or [])
            impacted_node_ids.update(str(node_id) for node_id in result.get("impacted_nodes", []) or [])
        for node_id in sorted(impacted_node_ids):
            try:
                node = self.graph_store.get_node(node_id)
            except KeyError:
                continue
            if node.status != TaskNodeStatus.READY:
                continue
            dispatchable = self._node_still_dispatchable(node, timestamp)
            if not dispatchable.success:
                self._block_node(node, dispatchable.error_code, metadata=dispatchable.metadata)

    def debug_snapshot(self) -> dict[str, Any]:
        return self.debug_exporter.snapshot(self)

    def export_dot(self, task_graph_id: str | None = None) -> str:
        return self.debug_exporter.export_dot(self, task_graph_id=task_graph_id)

    def provider_status_summary(self) -> dict[str, Any]:
        if self.kernel_service is None:
            return {"state": "unavailable", "error_code": "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE"}
        try:
            status = self.kernel_service.kernel_status()
        except Exception as exc:
            return {
                "state": "unavailable",
                "error_code": "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE",
                "failure": _provider_status_failure(exc),
            }
        providers = status.get("providers", {}) if isinstance(status, dict) else {}
        return {
            "llm": _provider_summary(providers.get("llm", {})),
            "skill": _provider_summary(providers.get("skill", {})),
            "ros_bridge": _provider_summary(providers.get("ros_bridge", {})),
        }

    def on_agent_suspended(self, agent_id: str, *, reason: str = "", held_syscall_ids: list[str] | None = None) -> None:
        self.lifecycle_hooks.on_suspended(agent_id, reason=reason, held_syscall_ids=held_syscall_ids)

    def on_agent_resumed(self, agent_id: str, *, reason: str = "", resumed_syscall_ids: list[str] | None = None) -> None:
        self.lifecycle_hooks.on_resumed(agent_id, reason=reason, resumed_syscall_ids=resumed_syscall_ids)
        self.refresh_ready_nodes()

    def on_agent_terminal(self, agent_id: str, *, event_type: str, reason: str = "", cancelled_syscall_ids: list[str] | None = None) -> None:
        self.lifecycle_hooks.on_terminal(agent_id, event_type=event_type, reason=reason, cancelled_syscall_ids=cancelled_syscall_ids)

    def _agent_allows_execution(self, node: TaskNode) -> KernelResponse:
        if self.agent_lifecycle is None:
            return KernelResponse.ok()
        decision = self.agent_lifecycle.admit_syscall(agent_id=node.agent_id, operation_type=node.operation_type)
        if decision.success:
            return decision
        metadata = dict(decision.metadata or {})
        metadata.pop("agent_id", None)
        return KernelResponse.error(
            "SCHEDULER_AGENT_NOT_RUNNABLE",
            metadata={
                **metadata,
                "operation_type": node.operation_type,
                "upstream_error_code": decision.error_code,
            },
        )

    def _node_still_dispatchable(self, node: TaskNode, timestamp: int) -> KernelResponse:
        runnable = self._agent_allows_execution(node)
        if not runnable.success:
            return runnable
        preconditions = self.precondition_evaluator.evaluate(node.preconditions, timestamp)
        if not preconditions.success:
            return KernelResponse.error(preconditions.error_code, metadata=preconditions.metadata)
        return KernelResponse.ok()

    def _block_node(self, node: TaskNode, error_code: str, *, metadata: dict[str, Any] | None = None) -> None:
        self.graph_store.mark_status(node.node_id, TaskNodeStatus.BLOCKED, error_code=error_code)
        self.ready_queue.remove(node.node_id)
        self.audit.emit(
            "scheduler.node.blocked",
            success=False,
            error_code=error_code,
            agent_id=node.agent_id,
            app_id=node.app_id,
            session_id=node.session_id,
            task_graph_id=node.task_graph_id,
            node_id=node.node_id,
            **dict(metadata or {}),
        )

    def _lane_has_capacity(self, node: TaskNode) -> bool:
        lane = self._lane_spec_for_node(node)
        if lane is None:
            return True
        running_count = self._running_count_for_queue(lane.queue_name)
        capacity = max(1, lane.max_workers if lane.concurrent else 1)
        return running_count < capacity

    def _lane_spec_for_node(self, node: TaskNode):
        queue_name = self.lane_mapper.queue_name_for(node)
        for lane in self.lanes:
            if lane.queue_name == queue_name:
                return lane
        return None

    def _running_count_for_queue(self, queue_name: str) -> int:
        count = 0
        for running_node_id in self.graph_store.global_dag.running_set:
            try:
                running_node = self.graph_store.get_node(running_node_id)
            except KeyError:
                continue
            if self.lane_mapper.queue_name_for(running_node) == queue_name:
                count += 1
        return count

    def _defer_for_lane_capacity(self, node: TaskNode) -> None:
        self.audit.emit(
            "scheduler.node.blocked",
            success=False,
            error_code="SCHEDULER_LANE_CAPACITY_FULL",
            agent_id=node.agent_id,
            app_id=node.app_id,
            session_id=node.session_id,
            task_graph_id=node.task_graph_id,
            node_id=node.node_id,
            lane=self.lane_mapper.derive_lane(node),
            queue_name=self.lane_mapper.queue_name_for(node),
        )

    def _requeue_deferred_nodes(self, nodes: list[TaskNode], timestamp: int) -> None:
        for node in nodes:
            if node.status != TaskNodeStatus.READY:
                continue
            key = self.priority_scorer.score(node, timestamp)
            self.ready_queue.push(node.node_id, key)

    def _dispatch_node(self, node: TaskNode) -> dict[str, Any]:
        if self.dispatch_adapter is None:
            self.graph_store.mark_status(node.node_id, TaskNodeStatus.FAILED, error_code="SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE")
            self.audit.emit(
                "scheduler.node.failed",
                success=False,
                error_code="SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
            )
            return {"node_id": node.node_id, "success": False, "error_code": "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE"}
        lease_result = self.resource_arbiter.try_acquire(node)
        if not lease_result.success:
            self.graph_store.mark_status(node.node_id, TaskNodeStatus.BLOCKED, error_code=lease_result.error_code)
            self.audit.emit(
                "scheduler.node.blocked",
                success=False,
                error_code=lease_result.error_code,
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
            )
            return {"node_id": node.node_id, "success": False, "error_code": lease_result.error_code}
        self.graph_store.mark_status(node.node_id, TaskNodeStatus.RUNNING)
        dispatch = self.dispatch_adapter.dispatch(node, lease_result.leases, scheduler_revision=self.graph_store.revision)
        self.resource_arbiter.bind_syscall(node, dispatch.syscall_id)
        binding_result = self._verify_dispatch_syscall_bound(node, dispatch)
        lease_ids = {lease.lease_id for lease in lease_result.leases}
        expired_dispatch_leases = self.resource_arbiter.expire(now_ns(), lease_ids=lease_ids)
        final_status = TaskNodeStatus.FAILED
        final_error_code = dispatch.error_code
        final_event = "scheduler.node.failed"
        final_success = False
        final_metadata: dict[str, Any] = {}
        if not binding_result.success:
            node.result = _response_to_mapping(dispatch.response)
            final_error_code = binding_result.error_code
            final_metadata = dict(binding_result.metadata)
        elif expired_dispatch_leases:
            node.result = _response_to_mapping(dispatch.response)
            cleanup_error_code = next((str(lease.metadata.get("expiration_error_code") or "") for lease in expired_dispatch_leases if lease.metadata.get("expiration_error_code")), "")
            final_status = TaskNodeStatus.FAILED if cleanup_error_code else TaskNodeStatus.STALE
            final_error_code = cleanup_error_code or "SCHEDULER_RESOURCE_LEASE_EXPIRED"
            final_event = "scheduler.node.failed" if cleanup_error_code else "scheduler.node.stale"
            final_metadata = {
                "resource_lease_id": ",".join(lease.lease_id for lease in expired_dispatch_leases),
                "lease_statuses": {lease.lease_id: lease.status for lease in expired_dispatch_leases},
                "cleanup_error_code": cleanup_error_code,
                "dispatch_success": dispatch.success,
            }
        elif dispatch.success:
            node.result = _response_to_mapping(dispatch.response)
            ingest_result = self._ingest_node_result(node, dispatch.response, dispatch.metadata or {})
            if ingest_result.success:
                final_status = TaskNodeStatus.COMPLETED
                final_error_code = ""
                final_event = "scheduler.node.completed"
                final_success = True
            else:
                final_error_code = ingest_result.error_code
                final_metadata = dict(ingest_result.metadata)
        else:
            node.result = _response_to_mapping(dispatch.response)
        release_result = self.resource_arbiter.release(lease_result.leases) if not expired_dispatch_leases else None
        if release_result is not None and not release_result.success:
            release_metadata = dict(release_result.metadata)
            resource_lease_id = str(release_metadata.pop("resource_lease_id", "") or ",".join(lease.lease_id for lease in lease_result.leases))
            self.graph_store.mark_status(node.node_id, TaskNodeStatus.FAILED, error_code=release_result.error_code)
            self.audit.emit(
                "scheduler.node.failed",
                success=False,
                error_code=release_result.error_code,
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                syscall_id=dispatch.syscall_id,
                resource_lease_id=resource_lease_id,
                prior_error_code=final_error_code,
                **release_metadata,
            )
        else:
            self.graph_store.mark_status(node.node_id, final_status, error_code=final_error_code)
            self.audit.emit(
                final_event,
                success=final_success,
                error_code=final_error_code,
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                syscall_id=dispatch.syscall_id,
                **final_metadata,
            )
        self.refresh_ready_nodes()
        stored_node = self.graph_store.get_node(node.node_id)
        success = dispatch.success and stored_node.status == TaskNodeStatus.COMPLETED
        return {"node_id": node.node_id, "success": success, "error_code": stored_node.error_code or dispatch.error_code, "syscall_id": dispatch.syscall_id}

    def _verify_dispatch_syscall_bound(self, node: TaskNode, dispatch) -> KernelResponse:
        if self.agent_lifecycle is None:
            return KernelResponse.ok()
        if not dispatch.syscall_id:
            return KernelResponse.ok()
        bound_agent_id = str(getattr(dispatch, "syscall_agent_id", "") or "")
        if bound_agent_id == node.agent_id:
            return KernelResponse.ok()
        return KernelResponse.error(
            "SCHEDULER_AGENT_NOT_RUNNABLE",
            metadata={
                "bound_agent_id": bound_agent_id,
                "reason": "dispatch returned syscall without matching ACB binding",
            },
        )

    def _ingest_node_result(self, node: TaskNode, response: Any, metadata: dict[str, Any]) -> KernelResponse:
        specs = list(node.metadata.get("produces_fact_specs") or [])
        if not specs:
            return KernelResponse.ok()
        if node.query_type == QueryType.LLM:
            return KernelResponse.error(
                "SCHEDULER_FACT_SOURCE_UNVERIFIED",
                metadata={"fact_key": ",".join(str(spec.get("fact_key") or spec.get("key") or "") for spec in specs)},
            )
        payload = _response_to_mapping(response)
        prepared: list[EnvironmentFact] = []
        for spec in specs:
            fact_key = str(spec.get("fact_key") or spec.get("key") or "")
            value_key = str(spec.get("value_key") or fact_key)
            if not fact_key or value_key not in payload:
                return KernelResponse.error(
                    "SCHEDULER_FACT_EXTRACTION_FAILED",
                    metadata={"fact_key": fact_key, "value_key": value_key},
                )
            source_audit_id = str(payload.get("audit_id") or metadata.get("audit_id") or "")
            if not source_audit_id:
                return KernelResponse.error(
                    "SCHEDULER_FACT_SOURCE_UNVERIFIED",
                    metadata={"fact_key": fact_key},
                )
            confidence_result = _extract_fact_confidence(payload, spec, fact_key=fact_key)
            if not confidence_result.success:
                return confidence_result
            real_dependency_result = _extract_real_dependency(payload, metadata, fact_key=fact_key)
            if not real_dependency_result.success:
                return real_dependency_result
            fact = EnvironmentFact.create(
                key=fact_key,
                value=payload[value_key],
                source_node_id=node.node_id,
                source_capability=node.capability,
                source_syscall_id=node.syscall_id,
                source_audit_id=source_audit_id,
                source_result=payload,
                ttl_ns=int(spec.get("ttl_ns", 30_000_000_000)),
                confidence=float(confidence_result.data),
                world_epoch=self.environment_store.world_epoch,
                schema_id=str(spec.get("schema_id") or ""),
                real_dependency=str(real_dependency_result.data),
                metadata={"task_graph_id": node.task_graph_id},
            )
            try:
                self.environment_store.validate_fact(fact)
            except SchedulerError as exc:
                return KernelResponse.error(exc.error_code, response_message=exc.message, metadata={"fact_key": fact_key, **exc.metadata})
            prepared.append(fact)
        for fact in prepared:
            self.environment_store.put(fact)
            self.audit.emit(
                "scheduler.environment.fact_created",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                syscall_id=node.syscall_id,
                fact_id=fact.fact_id,
                fact_key=fact.key,
            )
            self._apply_environment_fact_event("environment_fact_created", fact)
        return KernelResponse.ok({"fact_count": len(prepared)})


def _response_to_mapping(response: Any) -> dict[str, Any]:
    if hasattr(response, "as_mapping"):
        return dict(response.as_mapping())
    if hasattr(response, "to_dict"):
        return dict(response.to_dict())
    if isinstance(response, dict):
        return dict(response)
    return {"value": response}


def _extract_fact_confidence(payload: dict[str, Any], spec: dict[str, Any], *, fact_key: str) -> KernelResponse:
    confidence_key = str(spec.get("confidence_key") or "")
    if confidence_key:
        if confidence_key in payload:
            return _coerce_fact_confidence(payload[confidence_key], fact_key=fact_key, source="response")
        if "confidence" in spec:
            return _coerce_fact_confidence(spec["confidence"], fact_key=fact_key, source="contract")
        return KernelResponse.error(
            "SCHEDULER_FACT_EXTRACTION_FAILED",
            metadata={"fact_key": fact_key, "value_key": confidence_key, "reason": "confidence evidence missing"},
        )
    if "confidence" in spec:
        return _coerce_fact_confidence(spec["confidence"], fact_key=fact_key, source="contract")
    if "confidence" in payload:
        return _coerce_fact_confidence(payload["confidence"], fact_key=fact_key, source="response")
    return KernelResponse.error(
        "SCHEDULER_FACT_EXTRACTION_FAILED",
        metadata={"fact_key": fact_key, "value_key": "confidence", "reason": "confidence evidence missing"},
    )


def _coerce_fact_confidence(value: Any, *, fact_key: str, source: str) -> KernelResponse:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return KernelResponse.error(
            "SCHEDULER_FACT_EXTRACTION_FAILED",
            metadata={"fact_key": fact_key, "reason": "confidence must be numeric", "confidence_source": source},
        )
    return KernelResponse.ok(confidence, metadata={"confidence_source": source}, data=confidence)


def _extract_real_dependency(payload: dict[str, Any], metadata: dict[str, Any], *, fact_key: str) -> KernelResponse:
    for source_name, source in (("response", payload), ("dispatch_metadata", metadata)):
        for key in ("real_dependency", "backend"):
            value = str(source.get(key) or "")
            if value:
                return KernelResponse.ok(value, metadata={"real_dependency_source": source_name, "real_dependency_key": key}, data=value)
    return KernelResponse.error(
        "SCHEDULER_FACT_SOURCE_UNVERIFIED",
        metadata={"fact_key": fact_key, "reason": "real dependency evidence missing"},
    )


def _coerce_dynamic_event(event: DynamicGraphEvent | dict[str, Any]) -> DynamicGraphEvent:
    if isinstance(event, DynamicGraphEvent):
        return event
    if isinstance(event, dict):
        return DynamicGraphEvent.from_dict(event)
    raise TypeError("dynamic graph event must be a DynamicGraphEvent or mapping")


def _provider_summary(provider: Any) -> dict[str, Any]:
    if not isinstance(provider, dict):
        return {"status": "unknown"}
    return {
        "status": provider.get("status") or provider.get("state") or "",
        "error_code": provider.get("error_code") or "",
        "available_modes": provider.get("available_modes") or [],
        "missing": provider.get("missing") or [],
    }


def _provider_status_failure(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    return {
        "type": type(exc).__name__,
        "message_sha256": stable_hash_payload(message),
        "message_length": len(message),
    }
