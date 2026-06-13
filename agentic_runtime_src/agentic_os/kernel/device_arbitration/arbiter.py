from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeviceLease:
    lease_id: str
    resource: str
    owner: str
    reason: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "lease_id": self.lease_id,
            "resource": self.resource,
            "owner": self.owner,
            "reason": self.reason,
            "created_at": self.created_at,
        }


class DeviceArbiter:
    """Kernel resource lock manager for embodied devices."""

    def __init__(self) -> None:
        self._leases: dict[str, DeviceLease] = {}
        self._lock = Lock()

    def acquire(self, resource: str, owner: str, reason: str = "") -> dict[str, Any]:
        with self._lock:
            if resource in self._leases:
                lease = self._leases[resource]
                return {
                    "success": False,
                    "error_code": "DEVICE_RESOURCE_BUSY",
                    "resource": resource,
                    "owner": lease.owner,
                    "lease": lease.to_dict(),
                }
            lease = DeviceLease(
                lease_id=f"lease_{uuid4().hex}",
                resource=resource,
                owner=owner,
                reason=reason,
                created_at=utc_now(),
            )
            self._leases[resource] = lease
        return {"success": True, "lease": lease.to_dict()}

    def release(self, resource: str, owner: str) -> dict[str, Any]:
        with self._lock:
            lease = self._leases.get(resource)
            if lease is None:
                return {"success": False, "error_code": "DEVICE_RESOURCE_NOT_LOCKED", "resource": resource}
            if lease.owner != owner:
                return {
                    "success": False,
                    "error_code": "DEVICE_RESOURCE_OWNER_MISMATCH",
                    "resource": resource,
                    "owner": lease.owner,
                }
            self._leases.pop(resource)
        return {"success": True, "resource": resource}

    def status(self) -> dict[str, Any]:
        with self._lock:
            leases = {resource: lease.to_dict() for resource, lease in self._leases.items()}
        return {"leases": leases}

