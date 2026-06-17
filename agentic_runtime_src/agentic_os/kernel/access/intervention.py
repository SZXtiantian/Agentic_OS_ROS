from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from .policy import AccessDecision, AccessRequest


class InterventionProvider(Protocol):
    def request_confirmation(self, request: AccessRequest) -> AccessDecision:
        ...


class DenyByDefaultInterventionProvider:
    """Default safety posture for irreversible operations without a UI."""

    def request_confirmation(self, request: AccessRequest) -> AccessDecision:
        return AccessDecision(
            allowed=False,
            error_code="ACCESS_INTERVENTION_REQUIRED",
            reason="operation requires user intervention",
            requires_intervention=True,
            intervention_id=f"ivn_{uuid4().hex[:12]}",
        )


class AlwaysAllowTestInterventionProvider:
    """Test-only provider for exercising high-risk flows."""

    def request_confirmation(self, request: AccessRequest) -> AccessDecision:
        return AccessDecision(
            allowed=True,
            reason="test intervention allowed",
            requires_intervention=True,
            intervention_id=f"ivn_{uuid4().hex[:12]}",
        )
