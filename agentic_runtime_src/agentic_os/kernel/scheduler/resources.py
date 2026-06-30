from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentic_os.kernel.system_call.models import monotonic_id


@dataclass
class ResourceRequest:
    resource_id: str
    mode: str = "exclusive"
    amount: int = 1
    lease_ttl_ns: int = 30_000_000_000
    priority_ceiling: int = 0
    preemptible: bool = False
    reason: str = ""
    agent_resource_type: str = "scheduler_lease"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceRequest":
        return cls(
            resource_id=str(data.get("resource_id") or data.get("id") or ""),
            mode=str(data.get("mode") or "exclusive"),
            amount=int(data.get("amount", 1)),
            lease_ttl_ns=int(data.get("lease_ttl_ns", 30_000_000_000)),
            priority_ceiling=int(data.get("priority_ceiling", 0)),
            preemptible=bool(data.get("preemptible", False)),
            reason=str(data.get("reason") or ""),
            agent_resource_type=str(data.get("agent_resource_type") or "scheduler_lease"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceLease:
    lease_id: str
    resource_id: str
    holder_node_id: str
    holder_agent_id: str
    mode: str
    acquired_ns: int
    expires_ns: int
    holder_base_priority: int
    holder_inherited_priority: int = 0
    status: str = "acquired"
    agent_resource_handle_id: str = ""
    audit_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        resource_id: str,
        holder_node_id: str,
        holder_agent_id: str,
        mode: str,
        acquired_ns: int,
        lease_ttl_ns: int,
        holder_base_priority: int,
        holder_inherited_priority: int = 0,
    ) -> "ResourceLease":
        return cls(
            lease_id=monotonic_id("lease"),
            resource_id=resource_id,
            holder_node_id=holder_node_id,
            holder_agent_id=holder_agent_id,
            mode=mode,
            acquired_ns=acquired_ns,
            expires_ns=acquired_ns + max(1, lease_ttl_ns),
            holder_base_priority=holder_base_priority,
            holder_inherited_priority=holder_inherited_priority,
        )

    def expired(self, now_ns: int) -> bool:
        return self.status == "acquired" and now_ns >= self.expires_ns

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resource_conflicts(existing: ResourceLease, request: ResourceRequest) -> bool:
    if existing.status not in {"acquired", "release_failed"}:
        return False
    if existing.resource_id != request.resource_id:
        return False
    if existing.mode == "shared" and request.mode == "shared":
        return False
    return True
