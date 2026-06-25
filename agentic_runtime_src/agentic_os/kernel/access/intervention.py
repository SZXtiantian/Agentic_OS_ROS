from __future__ import annotations

import json
import os
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


class CliOperatorInterventionProvider:
    """Allows robot intervention only when the local CLI recorded operator consent."""

    def __init__(
        self,
        *,
        approval_env: str = "AGENTIC_OPERATOR_INTERVENTION_APPROVED",
        source_env: str = "AGENTIC_OPERATOR_INTERVENTION_SOURCE",
    ) -> None:
        self.approval_env = approval_env
        self.source_env = source_env

    def request_confirmation(self, request: AccessRequest) -> AccessDecision:
        intervention_id = f"ivn_{uuid4().hex[:12]}"
        if not _env_truthy(os.environ.get(self.approval_env, "")):
            return _intervention_required(intervention_id, "operation requires user intervention")

        resource_type = request.resource.resource_type.lower()
        resource_id = request.resource.resource_id.lower()
        if resource_type != "robot_motion":
            return _intervention_required(
                intervention_id,
                "CLI operator intervention is limited to robot motion requests",
            )
        if not _env_truthy(os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION", "")):
            return _intervention_required(
                intervention_id,
                "robot motion requires AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 or --allow-arm-motion",
            )
        if resource_id.startswith("manipulation.") and not _env_truthy(
            os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION", "")
        ):
            return _intervention_required(
                intervention_id,
                "manipulation requires AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION=1",
            )

        source = os.environ.get(self.source_env, "cli_operator")
        return AccessDecision(
            allowed=True,
            reason="operator CLI intervention allowed",
            requires_intervention=True,
            intervention_id=intervention_id,
            metadata={
                "operator_confirmation_source": source,
                "approval_env": self.approval_env,
            },
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


def _env_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _intervention_required(intervention_id: str, reason: str) -> AccessDecision:
    return AccessDecision(
        allowed=False,
        error_code="ACCESS_INTERVENTION_REQUIRED",
        reason=reason,
        requires_intervention=True,
        intervention_id=intervention_id,
    )
