from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .decision_log import access_decision_record
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


class ConsoleInterventionProvider:
    """Blocking console prompt for local development and operator dry runs."""

    def request_confirmation(self, request: AccessRequest) -> AccessDecision:
        intervention_id = f"ivn_{uuid4().hex[:12]}"
        prompt = (
            f"Allow high-risk operation {request.action} on "
            f"{request.resource.resource_type}:{request.resource.resource_id}? [y/N] "
        )
        answer = input(prompt).strip().lower()
        if answer in {"y", "yes"}:
            return AccessDecision(
                allowed=True,
                reason="operator console intervention allowed",
                requires_intervention=True,
                intervention_id=intervention_id,
            )
        return AccessDecision(
            allowed=False,
            error_code="ACCESS_INTERVENTION_DENIED",
            reason="operator console intervention denied",
            requires_intervention=True,
            intervention_id=intervention_id,
        )


class FileQueueInterventionProvider:
    """Queues intervention requests for an external operator UI."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def request_confirmation(self, request: AccessRequest) -> AccessDecision:
        intervention_id = f"ivn_{uuid4().hex[:12]}"
        decision = AccessDecision(
            allowed=False,
            error_code="ACCESS_INTERVENTION_REQUIRED",
            reason="operation queued for operator intervention",
            requires_intervention=True,
            intervention_id=intervention_id,
        )
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(access_decision_record(request, decision), sort_keys=True) + "\n")
        return decision
