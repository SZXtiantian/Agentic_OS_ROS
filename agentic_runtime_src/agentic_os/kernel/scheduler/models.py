from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def now_ns() -> int:
    return time.monotonic_ns()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash_payload(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TaskNodeStatus:
    CREATED = "created"
    ADMITTED = "admitted"
    WAITING = "waiting"
    READY = "ready"
    LEASED = "leased"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    STALE = "stale"
    REJECTED = "rejected"

    TERMINAL = {COMPLETED, FAILED, CANCELLED, STALE, REJECTED}
    EXECUTABLE = {ADMITTED, WAITING, BLOCKED}


class TaskGraphStatus:
    CREATED = "created"
    ADMITTED = "admitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIALLY_SUSPENDED = "partially_suspended"
    REJECTED = "rejected"


class EdgeType:
    PRECEDENCE = "precedence"
    PRODUCES_FACT = "produces_fact"
    CONSUMES_FACT = "consumes_fact"
    REUSES_FACT = "reuses_fact"
    MUTEX = "mutex"
    FACILITATES = "facilitates"
    HINDERS = "hinders"
    TEMPORAL = "temporal"
    SAFETY_BLOCK = "safety_block"


class QueryType:
    LLM = "llm"
    SKILL = "skill"
    ROBOT_CAPABILITY = "robot_capability"
    TOOL = "tool"
    MEMORY = "memory"
    STORAGE = "storage"
    CONTEXT = "context"
    HUMAN = "human"

    ALL = {LLM, SKILL, ROBOT_CAPABILITY, TOOL, MEMORY, STORAGE, CONTEXT, HUMAN}


class DispatchLaneName:
    EMERGENCY = "emergency"
    SAFETY = "safety"
    MOTION = "motion"
    PERCEPTION = "perception"
    LLM_TOOL = "llm_tool"
    IO_AUDIT = "io_audit"
    BACKGROUND = "background"


class PreemptPolicy:
    CANCELLABLE = "cancellable"
    CHECKPOINTABLE = "checkpointable"
    NON_PREEMPTIBLE = "non_preemptible"
    EMERGENCY_STOP_ONLY = "emergency_stop_only"


@dataclass(frozen=True)
class RouteIntent:
    route_id: str = ""
    workspace_zones: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RouteIntent | None":
        if not data:
            return None
        return cls(
            route_id=str(data.get("route_id") or ""),
            workspace_zones=list(data.get("workspace_zones") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "workspace_zones": list(self.workspace_zones or []),
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class CoverageRequirement:
    requirement_id: str
    workspace_zone: str = ""
    route_segment_id: str = ""
    required: bool = True
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CoverageRequirement":
        return cls(
            requirement_id=str(data.get("requirement_id") or data.get("id") or ""),
            workspace_zone=str(data.get("workspace_zone") or ""),
            route_segment_id=str(data.get("route_segment_id") or ""),
            required=bool(data.get("required", True)),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "workspace_zone": self.workspace_zone,
            "route_segment_id": self.route_segment_id,
            "required": self.required,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class FusionPolicy:
    allow_fact_reuse: bool = True
    allow_reordering: bool = True
    preserve_coverage: bool = True
    max_added_deadline_ns: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FusionPolicy":
        payload = dict(data or {})
        return cls(
            allow_fact_reuse=bool(payload.get("allow_fact_reuse", True)),
            allow_reordering=bool(payload.get("allow_reordering", True)),
            preserve_coverage=bool(payload.get("preserve_coverage", True)),
            max_added_deadline_ns=payload.get("max_added_deadline_ns"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_fact_reuse": self.allow_fact_reuse,
            "allow_reordering": self.allow_reordering,
            "preserve_coverage": self.preserve_coverage,
            "max_added_deadline_ns": self.max_added_deadline_ns,
        }
