from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol

from .policy import AccessRequest


VALID_EFFECTS = {"allow", "deny", "require_intervention"}


@dataclass(frozen=True)
class AccessRule:
    subject_agent: str = "*"
    subject_group: str = "*"
    action: str = "*"
    resource_type: str = "*"
    resource_id_pattern: str = "*"
    effect: str = "deny"
    expires_at: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        effect = self.effect.lower()
        if effect not in VALID_EFFECTS:
            raise ValueError(f"invalid access rule effect: {self.effect}")
        object.__setattr__(self, "effect", effect)

    def matches(self, request: AccessRequest, *, now: datetime | None = None) -> bool:
        if self.is_expired(now=now):
            return False
        return (
            self._matches_value(self.subject_agent, request.subject.agent_name)
            and self._matches_group(request.subject.groups)
            and self._matches_value(self.action, request.action)
            and self._matches_value(self.resource_type, request.resource.resource_type)
            and fnmatch(request.resource.resource_id, self.resource_id_pattern or "*")
        )

    def is_expired(self, *, now: datetime | None = None) -> bool:
        expires_at = _parse_timestamp(self.expires_at)
        if expires_at is None:
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return expires_at <= current

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "AccessRule":
        return cls(
            subject_agent=str(payload.get("subject_agent") or "*"),
            subject_group=str(payload.get("subject_group") or "*"),
            action=str(payload.get("action") or "*"),
            resource_type=str(payload.get("resource_type") or "*"),
            resource_id_pattern=str(payload.get("resource_id_pattern") or "*"),
            effect=str(payload.get("effect") or "deny"),
            expires_at=str(payload["expires_at"]) if payload.get("expires_at") else None,
            reason=str(payload.get("reason") or ""),
        )

    def _matches_value(self, pattern: str, value: str) -> bool:
        normalized_pattern = (pattern or "*").lower()
        normalized_value = (value or "").lower()
        return normalized_pattern == "*" or fnmatch(normalized_value, normalized_pattern)

    def _matches_group(self, groups: tuple[str, ...]) -> bool:
        pattern = (self.subject_group or "*").lower()
        if pattern == "*":
            return True
        return any(fnmatch(group.lower(), pattern) for group in groups)


class AccessStore(Protocol):
    def add_rule(self, rule: AccessRule) -> None:
        ...

    def list_rules(self) -> list[AccessRule]:
        ...

    def matching_rules(self, request: AccessRequest) -> list[AccessRule]:
        ...


class InMemoryAccessStore:
    def __init__(self, rules: list[AccessRule] | tuple[AccessRule, ...] | None = None) -> None:
        self._rules = list(rules or ())

    def add_rule(self, rule: AccessRule) -> None:
        self._rules.append(rule)

    def list_rules(self) -> list[AccessRule]:
        return list(self._rules)

    def matching_rules(self, request: AccessRequest) -> list[AccessRule]:
        return [rule for rule in self._rules if rule.matches(request)]


class JsonFileAccessStore:
    """Persistent dynamic ACL store backed by a JSON rule list."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def add_rule(self, rule: AccessRule) -> None:
        rules = self.list_rules()
        rules.append(rule)
        self._write_rules(rules)

    def list_rules(self) -> list[AccessRule]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid access rule store: {self.path}") from exc
        if not isinstance(payload, list):
            raise ValueError(f"access rule store must contain a JSON list: {self.path}")
        return [AccessRule.from_dict(item) for item in payload if isinstance(item, dict)]

    def matching_rules(self, request: AccessRequest) -> list[AccessRule]:
        return [rule for rule in self.list_rules() if rule.matches(request)]

    def _write_rules(self, rules: list[AccessRule]) -> None:
        payload = [rule.to_dict() for rule in rules]
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
