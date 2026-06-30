from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .audit import SchedulerAudit
from .models import now_ns
from .resources import ResourceLease, ResourceRequest, resource_conflicts
from .task_node import TaskNode


@dataclass
class LeaseResult:
    success: bool
    leases: list[ResourceLease] = field(default_factory=list)
    error_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ResourceArbiter:
    def __init__(self, *, agent_lifecycle=None, graph_store=None, audit: SchedulerAudit | None = None, device_arbiter=None) -> None:
        self.agent_lifecycle = agent_lifecycle
        self.graph_store = graph_store
        self.audit = audit or SchedulerAudit()
        self.device_arbiter = device_arbiter
        self._leases: dict[str, ResourceLease] = {}
        self._expired: dict[str, ResourceLease] = {}

    def try_acquire(self, node: TaskNode, at_ns: int | None = None) -> LeaseResult:
        timestamp = at_ns if at_ns is not None else now_ns()
        self.expire(timestamp)
        requested: list[ResourceRequest] = list(node.resources)
        for request in requested:
            self.audit.emit(
                "scheduler.resource.lease_requested",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                resource_id=request.resource_id,
            )
            conflict = self._first_conflict(request)
            if conflict is not None:
                self._inherit_priority(waiter=node, holder_lease=conflict)
                self.audit.emit(
                    "scheduler.resource.lease_rejected",
                    success=False,
                    error_code="SCHEDULER_RESOURCE_UNAVAILABLE",
                    agent_id=node.agent_id,
                    app_id=node.app_id,
                    session_id=node.session_id,
                    task_graph_id=node.task_graph_id,
                    node_id=node.node_id,
                    resource_lease_id=conflict.lease_id,
                    resource_id=request.resource_id,
                )
                return LeaseResult(False, error_code="SCHEDULER_RESOURCE_UNAVAILABLE", metadata={"resource_id": request.resource_id})

        device_locks: list[tuple[ResourceRequest, dict[str, Any]]] = []
        for request in requested:
            device_result = self._acquire_device(request, node)
            if not device_result.get("success", True):
                self._release_acquired_devices(device_locks, node)
                error_code = str(device_result.get("error_code") or "SCHEDULER_RESOURCE_UNAVAILABLE")
                self.audit.emit(
                    "scheduler.resource.lease_rejected",
                    success=False,
                    error_code="SCHEDULER_RESOURCE_UNAVAILABLE",
                    agent_id=node.agent_id,
                    app_id=node.app_id,
                    session_id=node.session_id,
                    task_graph_id=node.task_graph_id,
                    node_id=node.node_id,
                    resource_id=request.resource_id,
                    upstream_error_code=error_code,
                    upstream_owner=str(device_result.get("owner") or ""),
                )
                return LeaseResult(
                    False,
                    error_code="SCHEDULER_RESOURCE_UNAVAILABLE",
                    metadata={"resource_id": request.resource_id, "upstream_error_code": error_code},
                )
            device_locks.append((request, device_result))

        acquired: list[ResourceLease] = []
        for request, device_result in device_locks:
            self._apply_priority_ceiling(node, request)
            lease = ResourceLease.create(
                resource_id=request.resource_id,
                holder_node_id=node.node_id,
                holder_agent_id=node.agent_id,
                mode=request.mode,
                acquired_ns=timestamp,
                lease_ttl_ns=request.lease_ttl_ns,
                holder_base_priority=node.base_priority,
                holder_inherited_priority=node.inherited_priority,
            )
            lease.metadata.update(
                {
                    "app_id": node.app_id,
                    "session_id": node.session_id,
                    "task_graph_id": node.task_graph_id,
                }
            )
            self._attach_device_metadata(lease, node, device_result)
            if self.agent_lifecycle is not None and node.agent_id:
                handle_id = self.agent_lifecycle.register_resource(
                    agent_id=node.agent_id,
                    resource_type=request.agent_resource_type,
                    resource_id=request.resource_id,
                    backend="scheduler.resource_arbiter",
                    session_id=node.session_id,
                    skill_call_id=node.node_id,
                    syscall_id=node.syscall_id,
                    lease_id=lease.lease_id,
                    metadata={"mode": request.mode, "reason": request.reason},
                )
                lease.agent_resource_handle_id = handle_id
            lease.audit_id = self.audit.emit(
                "scheduler.resource.lease_acquired",
                agent_id=node.agent_id,
                app_id=node.app_id,
                session_id=node.session_id,
                task_graph_id=node.task_graph_id,
                node_id=node.node_id,
                resource_lease_id=lease.lease_id,
                resource_id=request.resource_id,
            )
            self._leases[lease.lease_id] = lease
            acquired.append(lease)
        node.resource_lease_ids = [lease.lease_id for lease in acquired]
        return LeaseResult(True, leases=acquired)

    def release(self, leases: list[ResourceLease] | list[str], *, reason: str = "node_finished") -> LeaseResult:
        released: list[ResourceLease] = []
        for item in leases:
            lease_id = item if isinstance(item, str) else item.lease_id
            lease = self._leases.get(lease_id)
            if lease is None:
                continue
            device_release = self._release_device(lease)
            if not device_release.get("success", True):
                self._mark_acb_release_failed(lease, "SCHEDULER_RESOURCE_RELEASE_FAILED", "scheduler device resource release failed")
                self.audit.emit(
                    "scheduler.resource.lease_release_failed",
                    success=False,
                    error_code="SCHEDULER_RESOURCE_RELEASE_FAILED",
                    agent_id=lease.holder_agent_id,
                    node_id=lease.holder_node_id,
                    resource_lease_id=lease.lease_id,
                    resource_id=lease.resource_id,
                    reason=reason,
                    upstream_error_code=device_release.get("error_code", ""),
                )
                return LeaseResult(
                    False,
                    error_code="SCHEDULER_RESOURCE_RELEASE_FAILED",
                    leases=released,
                    metadata={
                        "resource_id": lease.resource_id,
                        "resource_lease_id": lease.lease_id,
                        "holder_node_id": lease.holder_node_id,
                        "holder_agent_id": lease.holder_agent_id,
                        "upstream_error_code": device_release.get("error_code"),
                    },
                )
            lease.status = "released"
            if self.agent_lifecycle is not None and lease.agent_resource_handle_id:
                try:
                    self.agent_lifecycle.mark_resource_released(lease.agent_resource_handle_id)
                except Exception:
                    self._mark_acb_release_failed(lease, "SCHEDULER_RESOURCE_RELEASE_FAILED", "scheduler resource release failed")
                    self.audit.emit(
                        "scheduler.resource.lease_release_failed",
                        success=False,
                        error_code="SCHEDULER_RESOURCE_RELEASE_FAILED",
                        agent_id=lease.holder_agent_id,
                        node_id=lease.holder_node_id,
                        resource_lease_id=lease.lease_id,
                        resource_id=lease.resource_id,
                        reason=reason,
                    )
                    return LeaseResult(
                        False,
                        error_code="SCHEDULER_RESOURCE_RELEASE_FAILED",
                        leases=released,
                        metadata={
                            "resource_id": lease.resource_id,
                            "resource_lease_id": lease.lease_id,
                            "holder_node_id": lease.holder_node_id,
                            "holder_agent_id": lease.holder_agent_id,
                        },
                    )
            self._leases.pop(lease_id, None)
            self.audit.emit(
                "scheduler.resource.lease_released",
                agent_id=lease.holder_agent_id,
                app_id=str(lease.metadata.get("app_id") or ""),
                session_id=str(lease.metadata.get("session_id") or ""),
                task_graph_id=str(lease.metadata.get("task_graph_id") or ""),
                node_id=lease.holder_node_id,
                resource_lease_id=lease.lease_id,
                resource_id=lease.resource_id,
                reason=reason,
            )
            released.append(lease)
        return LeaseResult(True, leases=released)

    def release_by_agent(self, agent_id: str, *, reason: str) -> LeaseResult:
        leases = [lease for lease in self._leases.values() if lease.holder_agent_id == agent_id]
        return self.release([lease.lease_id for lease in leases], reason=reason)

    def bind_syscall(self, node: TaskNode, syscall_id: str) -> None:
        if not syscall_id:
            return
        for lease_id in list(node.resource_lease_ids):
            lease = self._leases.get(lease_id)
            if lease is None:
                continue
            lease.metadata["syscall_id"] = syscall_id
            if self.agent_lifecycle is None or not lease.agent_resource_handle_id:
                continue
            handle = self.agent_lifecycle.resource_registry.get(lease.agent_resource_handle_id)
            if handle is not None:
                handle.syscall_id = syscall_id
                handle.metadata["syscall_id"] = syscall_id
        self.audit.emit(
            "scheduler.resource.lease_bound",
            agent_id=node.agent_id,
            app_id=node.app_id,
            session_id=node.session_id,
            task_graph_id=node.task_graph_id,
            node_id=node.node_id,
            syscall_id=syscall_id,
            resource_lease_id=",".join(node.resource_lease_ids),
        )

    def expire(self, at_ns: int | None = None, *, lease_ids: set[str] | None = None) -> list[ResourceLease]:
        timestamp = at_ns if at_ns is not None else now_ns()
        expired: list[ResourceLease] = []
        for lease_id, lease in list(self._leases.items()):
            if lease_ids is not None and lease_id not in lease_ids:
                continue
            if lease.expired(timestamp):
                device_release = self._release_device(lease)
                if not device_release.get("success", True):
                    self._mark_expired_release_failed(
                        lease,
                        upstream_error_code=str(device_release.get("error_code") or ""),
                        reason="scheduler expired device resource release failed",
                    )
                    expired.append(lease)
                    continue
                if self.agent_lifecycle is not None and lease.agent_resource_handle_id:
                    try:
                        self.agent_lifecycle.mark_resource_released(lease.agent_resource_handle_id)
                    except Exception:
                        self._mark_expired_release_failed(lease, reason="scheduler expired resource release failed")
                        expired.append(lease)
                        continue
                self._leases.pop(lease_id, None)
                lease.status = "expired"
                self._expired[lease_id] = lease
                self.audit.emit(
                    "scheduler.resource.lease_expired",
                    success=False,
                    error_code="SCHEDULER_RESOURCE_LEASE_EXPIRED",
                    agent_id=lease.holder_agent_id,
                    app_id=str(lease.metadata.get("app_id") or ""),
                    session_id=str(lease.metadata.get("session_id") or ""),
                    task_graph_id=str(lease.metadata.get("task_graph_id") or ""),
                    node_id=lease.holder_node_id,
                    resource_lease_id=lease.lease_id,
                    resource_id=lease.resource_id,
                    upstream_error_code="" if device_release.get("success", True) else device_release.get("error_code", ""),
                )
                expired.append(lease)
        return expired

    def snapshot(self) -> dict[str, Any]:
        return {
            "leases": {lease_id: lease.to_dict() for lease_id, lease in sorted(self._leases.items())},
            "expired_leases": {lease_id: lease.to_dict() for lease_id, lease in sorted(self._expired.items())},
        }

    def _first_conflict(self, request: ResourceRequest) -> ResourceLease | None:
        for lease in self._leases.values():
            if resource_conflicts(lease, request):
                return lease
        return None

    def _inherit_priority(self, *, waiter: TaskNode, holder_lease: ResourceLease) -> None:
        if waiter.effective_priority <= holder_lease.holder_base_priority + holder_lease.holder_inherited_priority:
            return
        holder_lease.holder_inherited_priority = max(holder_lease.holder_inherited_priority, waiter.effective_priority)
        holder_node = self._holder_node(holder_lease.holder_node_id)
        if holder_node is not None:
            holder_node.inherited_priority = max(holder_node.inherited_priority, waiter.effective_priority)
            holder_node.effective_priority = max(holder_node.effective_priority, holder_node.inherited_priority)
            if self.graph_store is not None and hasattr(self.graph_store, "apply_changed_nodes"):
                self.graph_store.apply_changed_nodes([holder_node.node_id])
        self.audit.emit(
            "scheduler.resource.priority_inheritance",
            agent_id=holder_lease.holder_agent_id,
            node_id=holder_lease.holder_node_id,
            resource_lease_id=holder_lease.lease_id,
            inherited_priority=holder_lease.holder_inherited_priority,
            holder_effective_priority=getattr(holder_node, "effective_priority", ""),
        )

    def _apply_priority_ceiling(self, node: TaskNode, request: ResourceRequest) -> None:
        if request.priority_ceiling <= 0:
            return
        if node.effective_priority >= request.priority_ceiling:
            return
        node.inherited_priority = max(node.inherited_priority, request.priority_ceiling)
        node.effective_priority = max(node.effective_priority, request.priority_ceiling)
        self.audit.emit(
            "scheduler.resource.priority_inheritance",
            agent_id=node.agent_id,
            node_id=node.node_id,
            resource_id=request.resource_id,
            inherited_priority=node.inherited_priority,
            reason="priority_ceiling",
        )

    def _holder_node(self, node_id: str) -> TaskNode | None:
        if self.graph_store is None:
            return None
        try:
            return self.graph_store.get_node(node_id)
        except Exception:
            return None

    def _acquire_device(self, request: ResourceRequest, node: TaskNode) -> dict[str, Any]:
        if self.device_arbiter is None:
            return {"success": True}
        try:
            result = self.device_arbiter.acquire(
                request.resource_id,
                node.node_id,
                reason=request.reason or f"scheduler:{node.capability}",
            )
        except Exception as exc:
            return {"success": False, "error_code": "SCHEDULER_DEVICE_ARBITER_ERROR", "reason": str(exc)}
        return dict(result or {"success": True})

    def _release_device(self, lease: ResourceLease) -> dict[str, Any]:
        if self.device_arbiter is None:
            return {"success": True}
        owner = str(lease.metadata.get("device_owner") or lease.holder_node_id)
        try:
            result = self.device_arbiter.release(lease.resource_id, owner)
        except Exception as exc:
            return {"success": False, "error_code": "SCHEDULER_DEVICE_ARBITER_ERROR", "reason": str(exc)}
        return dict(result or {"success": True})

    def _release_acquired_devices(self, locks: list[tuple[ResourceRequest, dict[str, Any]]], node: TaskNode) -> None:
        if self.device_arbiter is None:
            return
        for request, _result in reversed(locks):
            try:
                self.device_arbiter.release(request.resource_id, node.node_id)
            except Exception:
                continue

    def _attach_device_metadata(self, lease: ResourceLease, node: TaskNode, device_result: dict[str, Any]) -> None:
        lease.metadata["device_owner"] = node.node_id
        device_lease = device_result.get("lease")
        if isinstance(device_lease, dict):
            lease.metadata["device_lease_id"] = str(device_lease.get("lease_id") or "")

    def _mark_acb_release_failed(self, lease: ResourceLease, error_code: str, message: str) -> None:
        if self.agent_lifecycle is None or not lease.agent_resource_handle_id:
            return
        self.agent_lifecycle.mark_resource_release_failed(lease.agent_resource_handle_id, error_code, message)

    def _mark_expired_release_failed(self, lease: ResourceLease, *, upstream_error_code: str = "", reason: str) -> None:
        lease.status = "release_failed"
        lease.metadata["expiration_error_code"] = "SCHEDULER_RESOURCE_RELEASE_FAILED"
        if upstream_error_code:
            lease.metadata["upstream_error_code"] = upstream_error_code
        self._mark_acb_release_failed(lease, "SCHEDULER_RESOURCE_RELEASE_FAILED", reason)
        self.audit.emit(
            "scheduler.resource.lease_release_failed",
            success=False,
            error_code="SCHEDULER_RESOURCE_RELEASE_FAILED",
            agent_id=lease.holder_agent_id,
            app_id=str(lease.metadata.get("app_id") or ""),
            session_id=str(lease.metadata.get("session_id") or ""),
            task_graph_id=str(lease.metadata.get("task_graph_id") or ""),
            node_id=lease.holder_node_id,
            resource_lease_id=lease.lease_id,
            resource_id=lease.resource_id,
            reason="lease_expired",
            upstream_error_code=upstream_error_code,
        )
        self.audit.emit(
            "scheduler.resource.lease_expired",
            success=False,
            error_code="SCHEDULER_RESOURCE_LEASE_EXPIRED",
            agent_id=lease.holder_agent_id,
            app_id=str(lease.metadata.get("app_id") or ""),
            session_id=str(lease.metadata.get("session_id") or ""),
            task_graph_id=str(lease.metadata.get("task_graph_id") or ""),
            node_id=lease.holder_node_id,
            resource_lease_id=lease.lease_id,
            resource_id=lease.resource_id,
            cleanup_error_code="SCHEDULER_RESOURCE_RELEASE_FAILED",
            upstream_error_code=upstream_error_code,
        )
