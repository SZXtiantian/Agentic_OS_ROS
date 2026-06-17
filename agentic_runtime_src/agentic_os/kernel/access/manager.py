from __future__ import annotations

from .intervention import DenyByDefaultInterventionProvider, InterventionProvider
from .policy import AccessDecision, AccessPolicy, AccessRequest, DefaultAccessPolicy, requires_intervention


class AccessManager:
    """Kernel access control layer for resources, sessions, and high-risk actions."""

    def __init__(
        self,
        policy: AccessPolicy | None = None,
        intervention_provider: InterventionProvider | None = None,
    ) -> None:
        self.policy = policy or DefaultAccessPolicy()
        self.intervention_provider = intervention_provider or DenyByDefaultInterventionProvider()

    def check(self, request: AccessRequest) -> AccessDecision:
        decision = self.policy.evaluate(request)
        if not decision.allowed:
            return decision
        if requires_intervention(request):
            return self.intervention_provider.request_confirmation(request)
        return decision

    def assert_allowed(self, request: AccessRequest) -> None:
        decision = self.check(request)
        if not decision.allowed:
            raise PermissionError(f"{decision.error_code}: {decision.reason}")
