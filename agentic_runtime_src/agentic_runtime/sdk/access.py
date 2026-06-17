from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agentic_os.kernel.access import AccessRequest, AccessResource, AccessSubject


class KernelAccessDeniedError(PermissionError):
    def __init__(self, error_code: str, reason: str) -> None:
        self.error_code = error_code
        self.reason = reason
        super().__init__(f"{error_code}: {reason}")


class KernelAccessAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def check(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        *,
        owner_agent: str = "",
        owner_user: str = "",
        labels: Iterable[str] = (),
        groups: Iterable[str] = (),
        irreversible: bool = False,
        reason: str = "",
    ) -> dict[str, Any]:
        manager = self._access_manager()
        decision = manager.check(
            AccessRequest(
                subject=AccessSubject(
                    agent_name=self.ctx.app_manifest.name,
                    app_id=self.ctx.app_manifest.name,
                    session_id=self.ctx.session_id,
                    groups=tuple(groups),
                    permissions=tuple(self.ctx.app_manifest.permissions),
                ),
                action=action,
                resource=AccessResource(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    owner_agent=owner_agent,
                    owner_user=owner_user,
                    labels=tuple(labels),
                ),
                irreversible=irreversible,
                reason=reason,
            )
        )
        return {
            "allowed": decision.allowed,
            "error_code": decision.error_code,
            "reason": decision.reason,
            "requires_intervention": decision.requires_intervention,
            "intervention_id": decision.intervention_id,
            "metadata": dict(decision.metadata),
        }

    async def assert_allowed(self, *args, **kwargs) -> dict[str, Any]:
        decision = await self.check(*args, **kwargs)
        if not decision["allowed"]:
            raise KernelAccessDeniedError(decision["error_code"], decision["reason"])
        return decision

    def _access_manager(self):
        service = self.ctx.kernel_service
        if service is None or not hasattr(service, "access_manager"):
            raise RuntimeError("kernel access manager is not available on this AgentContext")
        return service.access_manager
