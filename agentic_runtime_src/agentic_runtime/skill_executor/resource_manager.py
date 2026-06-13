from __future__ import annotations

from dataclasses import dataclass

from agentic_os.kernel.device_arbitration import DeviceArbiter

from agentic_runtime.errors import ResourceLockedError


@dataclass(frozen=True)
class ResourceLease:
    resource: str
    session_id: str
    skill_call_id: str


class ResourceManager:
    def __init__(self) -> None:
        self.kernel = DeviceArbiter()
        self._leases: dict[str, ResourceLease] = {}

    def acquire(self, resource: str, session_id: str, skill_call_id: str) -> ResourceLease:
        existing = self._leases.get(resource)
        if existing and existing.session_id != session_id:
            raise ResourceLockedError(f"{resource} locked by {existing.session_id}")
        if existing and existing.skill_call_id != skill_call_id:
            raise ResourceLockedError(f"{resource} already locked by this session")
        if existing:
            return existing
        owner = f"{session_id}:{skill_call_id}"
        result = self.kernel.acquire(resource, owner, reason="skill_execution")
        if not result.get("success"):
            raise ResourceLockedError(f"{resource} locked by {result.get('owner', 'unknown')}")
        lease = ResourceLease(resource, session_id, skill_call_id)
        self._leases[resource] = lease
        return lease

    def release(self, resource: str, session_id: str, skill_call_id: str) -> None:
        existing = self._leases.get(resource)
        if existing and existing.session_id == session_id and existing.skill_call_id == skill_call_id:
            self.kernel.release(resource, f"{session_id}:{skill_call_id}")
            self._leases.pop(resource, None)

    def release_by_session(self, session_id: str) -> None:
        for resource, lease in list(self._leases.items()):
            if lease.session_id == session_id:
                self.kernel.release(resource, f"{lease.session_id}:{lease.skill_call_id}")
                self._leases.pop(resource, None)

    def snapshot(self) -> dict[str, str]:
        return {
            resource: f"{lease.session_id}:{lease.skill_call_id}"
            for resource, lease in sorted(self._leases.items())
        }
