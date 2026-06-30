from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from .errors import SchedulerResult


SUPPORTED_OPERATORS = {
    "exists",
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "contains",
    "matches_schema",
    "within_workspace_zone",
    "pose_within_tolerance",
}


@dataclass(frozen=True)
class Precondition:
    fact_key: str
    operator: str = "exists"
    expected: Any = None
    min_confidence: float | None = None
    max_age_ns: int | None = None
    required_schema_id: str = ""
    require_current_world_epoch: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Precondition":
        return cls(
            fact_key=str(data.get("fact_key") or data.get("key") or ""),
            operator=str(data.get("operator") or "exists"),
            expected=data.get("expected"),
            min_confidence=data.get("min_confidence"),
            max_age_ns=data.get("max_age_ns"),
            required_schema_id=str(data.get("required_schema_id") or ""),
            require_current_world_epoch=bool(data.get("require_current_world_epoch", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PreconditionEvaluator:
    def __init__(self, environment_store) -> None:
        self.environment_store = environment_store

    def evaluate(self, preconditions: list[Precondition], now_ns: int) -> SchedulerResult:
        for precondition in preconditions:
            result = self.evaluate_one(precondition, now_ns)
            if not result.success:
                return result
        return SchedulerResult.ok()

    def evaluate_one(self, precondition: Precondition, now_ns: int) -> SchedulerResult:
        if precondition.operator not in SUPPORTED_OPERATORS:
            return SchedulerResult.error(
                "SCHEDULER_PRECONDITION_OPERATOR_UNSUPPORTED",
                operator=precondition.operator,
                fact_key=precondition.fact_key,
            )
        fact = self.environment_store.get(precondition.fact_key, now_ns=now_ns)
        if fact is None:
            expired_fact = self.environment_store.expired_fact_for_key(precondition.fact_key)
            if expired_fact is not None:
                if expired_fact.metadata.get("expired_reason") == "world_epoch_stale":
                    return SchedulerResult.error(
                        "SCHEDULER_FACT_WORLD_EPOCH_STALE",
                        fact_key=precondition.fact_key,
                        fact_id=expired_fact.fact_id,
                    )
                return SchedulerResult.error(
                    "SCHEDULER_FACT_STALE",
                    fact_key=precondition.fact_key,
                    fact_id=expired_fact.fact_id,
                )
            return SchedulerResult.error("SCHEDULER_FACT_NOT_FOUND", fact_key=precondition.fact_key)
        if not fact.source_is_verified():
            return SchedulerResult.error(
                "SCHEDULER_FACT_SOURCE_UNVERIFIED",
                fact_key=precondition.fact_key,
                fact_id=fact.fact_id,
            )
        if precondition.max_age_ns is not None and now_ns - fact.timestamp_ns > min(precondition.max_age_ns, fact.ttl_ns):
            return SchedulerResult.error("SCHEDULER_FACT_STALE", fact_key=precondition.fact_key)
        if precondition.min_confidence is not None and fact.confidence < precondition.min_confidence:
            return SchedulerResult.error("SCHEDULER_FACT_CONFIDENCE_LOW", fact_key=precondition.fact_key)
        if precondition.require_current_world_epoch and fact.world_epoch != self.environment_store.world_epoch:
            return SchedulerResult.error("SCHEDULER_FACT_WORLD_EPOCH_STALE", fact_key=precondition.fact_key)
        if precondition.required_schema_id and fact.schema_id != precondition.required_schema_id:
            return SchedulerResult.error("SCHEDULER_FACT_SCHEMA_INVALID", fact_key=precondition.fact_key)
        try:
            comparison_ok = _compare(fact.value, precondition.operator, precondition.expected)
        except (SchemaError, ValidationError) as exc:
            return SchedulerResult.error(
                "SCHEDULER_FACT_SCHEMA_INVALID",
                fact_key=precondition.fact_key,
                operator=precondition.operator,
                reason=str(exc),
            )
        except (TypeError, ValueError) as exc:
            return SchedulerResult.error(
                "SCHEDULER_PRECONDITION_NOT_MET",
                fact_key=precondition.fact_key,
                operator=precondition.operator,
                reason=str(exc),
            )
        if not comparison_ok:
            return SchedulerResult.error(
                "SCHEDULER_PRECONDITION_NOT_MET",
                fact_key=precondition.fact_key,
                operator=precondition.operator,
            )
        return SchedulerResult.ok()


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "exists":
        return actual is not None
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    if operator == "in":
        return actual in expected
    if operator == "contains":
        return expected in actual
    if operator == "matches_schema":
        Draft202012Validator.check_schema(expected)
        Draft202012Validator(expected).validate(actual)
        return True
    if operator == "within_workspace_zone":
        return _workspace_zone(actual) == str(expected)
    if operator == "pose_within_tolerance":
        return _pose_within_tolerance(actual, expected)
    return False


def _workspace_zone(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("workspace_zone") or value.get("zone") or "")
    return ""


def _pose_within_tolerance(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    tolerance = float(expected.get("tolerance", expected.get("tolerance_m", 0.0)) or 0.0)
    target = expected.get("pose") if isinstance(expected.get("pose"), dict) else expected
    for axis in ("x", "y", "z"):
        if axis in target and abs(float(actual.get(axis, 0.0)) - float(target.get(axis, 0.0))) > tolerance:
            return False
    return True
