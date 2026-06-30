from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from agentic_os.kernel.system_call.models import monotonic_id

from .errors import SchedulerError
from .models import now_ns, stable_hash_payload


@dataclass
class EnvironmentFact:
    fact_id: str
    key: str
    value: Any
    source_node_id: str
    source_capability: str
    source_syscall_id: str
    source_audit_id: str
    source_result_hash: str
    timestamp_ns: int
    ttl_ns: int
    confidence: float
    world_epoch: int
    schema_id: str
    real_dependency: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        key: str,
        value: Any,
        source_node_id: str,
        source_capability: str,
        source_syscall_id: str,
        source_audit_id: str,
        source_result: Any,
        ttl_ns: int,
        confidence: float,
        world_epoch: int,
        schema_id: str,
        real_dependency: str,
        metadata: dict[str, Any] | None = None,
    ) -> "EnvironmentFact":
        return cls(
            fact_id=monotonic_id("fact"),
            key=key,
            value=value,
            source_node_id=source_node_id,
            source_capability=source_capability,
            source_syscall_id=source_syscall_id,
            source_audit_id=source_audit_id,
            source_result_hash=stable_hash_payload(source_result),
            timestamp_ns=now_ns(),
            ttl_ns=max(1, int(ttl_ns)),
            confidence=float(confidence),
            world_epoch=int(world_epoch),
            schema_id=schema_id,
            real_dependency=real_dependency,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentFact":
        return cls(
            fact_id=str(data.get("fact_id") or monotonic_id("fact")),
            key=str(data["key"]),
            value=data.get("value"),
            source_node_id=str(data.get("source_node_id") or ""),
            source_capability=str(data.get("source_capability") or ""),
            source_syscall_id=str(data.get("source_syscall_id") or ""),
            source_audit_id=str(data.get("source_audit_id") or ""),
            source_result_hash=str(data.get("source_result_hash") or ""),
            timestamp_ns=int(data.get("timestamp_ns", now_ns())),
            ttl_ns=int(data.get("ttl_ns", 1)),
            confidence=float(data.get("confidence", 0.0)),
            world_epoch=int(data.get("world_epoch", 0)),
            schema_id=str(data.get("schema_id") or ""),
            real_dependency=str(data.get("real_dependency") or ""),
            metadata=dict(data.get("metadata") or {}),
        )

    def is_expired(self, at_ns: int) -> bool:
        return at_ns - self.timestamp_ns >= self.ttl_ns

    def source_is_verified(self) -> bool:
        return bool(
            self.source_node_id
            and self.source_capability
            and self.source_syscall_id
            and self.source_audit_id
            and self.source_result_hash
            and self.real_dependency
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EnvironmentStore:
    def __init__(
        self,
        schemas: dict[str, dict[str, Any]] | None = None,
        *,
        world_epoch: int = 0,
        schema_root: Path | None = None,
    ) -> None:
        self.world_epoch = world_epoch
        self._facts_by_key: dict[str, EnvironmentFact] = {}
        self._expired: dict[str, EnvironmentFact] = {}
        self._schemas = dict(schemas or {})
        self.schema_root = schema_root or Path(__file__).with_name("schemas")

    def register_schema(self, schema_id: str, schema: dict[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self._schemas[schema_id] = schema

    def get(self, fact_key: str, *, now_ns: int | None = None) -> EnvironmentFact | None:
        fact = self._facts_by_key.get(fact_key)
        if fact is None:
            return None
        at_ns = now_ns if now_ns is not None else globals()["now_ns"]()
        if fact.is_expired(at_ns):
            fact.metadata["expired_reason"] = "ttl_expired"
            fact.metadata["expired_at_ns"] = at_ns
            self._expired[fact.fact_id] = fact
            self._facts_by_key.pop(fact_key, None)
            return None
        return fact

    def put(self, fact: EnvironmentFact) -> EnvironmentFact:
        self.validate_fact(fact)
        self._facts_by_key[fact.key] = fact
        return fact

    def validate_fact(self, fact: EnvironmentFact) -> None:
        self._validate_fact(fact)

    def expire(self, at_ns: int) -> list[EnvironmentFact]:
        expired: list[EnvironmentFact] = []
        for key, fact in list(self._facts_by_key.items()):
            if fact.is_expired(at_ns) or fact.world_epoch != self.world_epoch:
                fact.metadata["expired_reason"] = "ttl_expired" if fact.is_expired(at_ns) else "world_epoch_stale"
                fact.metadata["expired_at_ns"] = at_ns
                self._facts_by_key.pop(key, None)
                self._expired[fact.fact_id] = fact
                expired.append(fact)
        return expired

    def validate_reuse(self, fact_key: str, *, min_confidence: float = 0.0, schema_id: str = "", at_ns: int | None = None) -> tuple[bool, dict[str, bool | str]]:
        fact = self.get(fact_key, now_ns=at_ns)
        if fact is None:
            expired_fact = self.expired_fact_for_key(fact_key)
            if expired_fact is not None:
                return False, {
                    "ttl_ok": False,
                    "confidence_ok": expired_fact.confidence >= min_confidence,
                    "schema_ok": not schema_id or expired_fact.schema_id == schema_id,
                    "world_epoch_ok": expired_fact.world_epoch == self.world_epoch,
                    "source_real_ok": expired_fact.source_is_verified(),
                    "reject_reason": "SCHEDULER_REUSE_TTL_OK_FAILED",
                    "fact_id": expired_fact.fact_id,
                    "source_node_id": expired_fact.source_node_id,
                }
            return False, {"reject_reason": "SCHEDULER_FACT_NOT_FOUND"}
        flags: dict[str, bool | str] = {
            "ttl_ok": not fact.is_expired(at_ns if at_ns is not None else now_ns()),
            "confidence_ok": fact.confidence >= min_confidence,
            "schema_ok": not schema_id or fact.schema_id == schema_id,
            "world_epoch_ok": fact.world_epoch == self.world_epoch,
            "source_real_ok": fact.source_is_verified(),
            "reject_reason": "",
        }
        accepted = all(bool(flags[name]) for name in ("ttl_ok", "confidence_ok", "schema_ok", "world_epoch_ok", "source_real_ok"))
        if not accepted:
            for key in ("ttl_ok", "confidence_ok", "schema_ok", "world_epoch_ok", "source_real_ok"):
                if not flags[key]:
                    flags["reject_reason"] = f"SCHEDULER_REUSE_{key.upper()}_FAILED"
                    break
        return accepted, flags

    def expired_fact_for_key(self, fact_key: str) -> EnvironmentFact | None:
        for fact in self._expired.values():
            if fact.key == fact_key:
                return fact
        return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "world_epoch": self.world_epoch,
            "facts": {key: fact.to_dict() for key, fact in sorted(self._facts_by_key.items())},
            "expired_facts": {key: fact.to_dict() for key, fact in sorted(self._expired.items())},
        }

    def _validate_fact(self, fact: EnvironmentFact) -> None:
        if not fact.source_is_verified():
            raise SchedulerError("SCHEDULER_FACT_SOURCE_UNVERIFIED", metadata={"fact_key": fact.key})
        self._validate_fact_record_schema(fact)
        if not 0.0 <= fact.confidence <= 1.0:
            raise SchedulerError("SCHEDULER_FACT_CONFIDENCE_LOW", metadata={"fact_key": fact.key, "confidence": fact.confidence})
        schema = self._schemas.get(fact.schema_id)
        if schema:
            try:
                Draft202012Validator(schema).validate(fact.value)
            except ValidationError as exc:
                raise SchedulerError("SCHEDULER_FACT_SCHEMA_INVALID", str(exc), {"fact_key": fact.key}) from exc

    def _validate_fact_record_schema(self, fact: EnvironmentFact) -> None:
        schema_path = self.schema_root / "environment_fact.schema.json"
        if not schema_path.exists():
            return
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(fact.to_dict())
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise SchedulerError("SCHEDULER_FACT_SCHEMA_INVALID", str(exc), {"fact_key": fact.key}) from exc
