from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .policy import AccessDecision, AccessRequest


SENSITIVE_KEY_PARTS = ("key", "password", "secret", "token")


class AccessDecisionLog(Protocol):
    def record(self, request: AccessRequest, decision: AccessDecision) -> None:
        ...


class InMemoryAccessDecisionLog:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, request: AccessRequest, decision: AccessDecision) -> None:
        self.records.append(access_decision_record(request, decision))


class JsonlAccessDecisionLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, request: AccessRequest, decision: AccessDecision) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(access_decision_record(request, decision), sort_keys=True) + "\n")


def access_decision_record(request: AccessRequest, decision: AccessDecision) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision_id": decision.decision_id,
        "subject": {
            "agent_name": request.subject.agent_name,
            "app_id": request.subject.app_id,
            "user_id": request.subject.user_id,
            "session_id": request.subject.session_id,
            "groups": list(request.subject.groups),
        },
        "action": request.action,
        "resource": {
            "resource_type": request.resource.resource_type,
            "resource_id": request.resource.resource_id,
            "owner_agent": request.resource.owner_agent,
            "owner_user": request.resource.owner_user,
            "labels": list(request.resource.labels),
        },
        "allowed": decision.allowed,
        "requires_intervention": decision.requires_intervention,
        "error_code": decision.error_code,
        "reason": decision.reason,
        "intervention_id": decision.intervention_id,
        "metadata": sanitize_metadata(decision.metadata),
    }


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(part in key_text.lower() for part in SENSITIVE_KEY_PARTS):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = sanitize_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_metadata(item) for item in value]
    return value
