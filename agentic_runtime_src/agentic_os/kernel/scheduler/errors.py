from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SCHEDULER_ERROR_CODES = {
    "SCHEDULER_DAG_CYCLE",
    "SCHEDULER_GRAPH_SCHEMA_INVALID",
    "SCHEDULER_NODE_SCHEMA_INVALID",
    "SCHEDULER_AGENT_NOT_RUNNABLE",
    "SCHEDULER_AGENT_EXITED",
    "SCHEDULER_AGENT_FAILED",
    "SCHEDULER_AGENT_CRASHED",
    "SCHEDULER_AGENT_KILLED",
    "SCHEDULER_AGENT_REAPED",
    "SCHEDULER_PRECONDITION_NOT_MET",
    "SCHEDULER_PRECONDITION_OPERATOR_UNSUPPORTED",
    "SCHEDULER_FACT_NOT_FOUND",
    "SCHEDULER_FACT_STALE",
    "SCHEDULER_FACT_CONFIDENCE_LOW",
    "SCHEDULER_FACT_WORLD_EPOCH_STALE",
    "SCHEDULER_FACT_SCHEMA_INVALID",
    "SCHEDULER_FACT_SOURCE_UNVERIFIED",
    "SCHEDULER_FACT_EXTRACTION_FAILED",
    "SCHEDULER_RESOURCE_UNAVAILABLE",
    "SCHEDULER_RESOURCE_LEASE_EXPIRED",
    "SCHEDULER_RESOURCE_RELEASE_FAILED",
    "SCHEDULER_DEVICE_ARBITER_ERROR",
    "SCHEDULER_LANE_CAPACITY_FULL",
    "SCHEDULER_LANE_UNSUPPORTED",
    "SCHEDULER_DEADLINE_UNSATISFIABLE",
    "SCHEDULER_DYNAMIC_EVENT_INVALID",
    "SCHEDULER_DYNAMIC_GRAPH_EVENT_FAILED",
    "SCHEDULER_GRAPH_NOT_FOUND",
    "SCHEDULER_GRAPH_REVISION_CONFLICT",
    "SCHEDULER_ADMISSION_REJECTED",
    "SCHEDULER_FUSION_REJECTED",
    "SCHEDULER_FUSION_CYCLE_REJECTED",
    "SCHEDULER_FUSION_COVERAGE_RISK",
    "SCHEDULER_FUSION_PLAN_NOT_ACCEPTED",
    "SCHEDULER_FUSION_COMMIT_INVALID",
    "SCHEDULER_FUSION_DUPLICATE_GRAPH_ID",
    "SCHEDULER_FUSION_DUPLICATE_NODE_ID",
    "SCHEDULER_FUSION_REUSE_EDGE_REJECTED",
    "SCHEDULER_FUSION_REUSE_PRODUCER_MISSING",
    "SCHEDULER_FUSION_REUSE_PRODUCER_NOT_IN_DAG",
    "SCHEDULER_FUSION_REUSE_CONSUMER_MISSING",
    "SCHEDULER_FUSION_REUSE_FACT_ID_MISSING",
    "SCHEDULER_FUSION_OPPORTUNITY_WINDOW_REQUIRED",
    "SCHEDULER_FUSION_INSERTION_NODE_MISSING",
    "SCHEDULER_FUSION_INSERTION_ANCHOR_MISSING",
    "SCHEDULER_FUSION_CROSS_GRAPH_REORDER_UNSUPPORTED",
    "SCHEDULER_FUSION_RESOURCE_INVALID",
    "SCHEDULER_FUSION_RESOURCE_WINDOW_UNAVAILABLE",
    "SCHEDULER_FUSION_SAFETY_INVALID",
    "SCHEDULER_FUSION_DEADLINE_INVALID",
    "SCHEDULER_FUSION_NODE_TERMINAL_INVALID",
    "SCHEDULER_FUSION_NO_REUSE_EDGE",
    "SCHEDULER_FUSION_REBASE_REQUIRED",
    "SCHEDULER_FUSION_REVISION_CONFLICT",
    "SCHEDULER_REUSE_TTL_OK_FAILED",
    "SCHEDULER_REUSE_CONFIDENCE_OK_FAILED",
    "SCHEDULER_REUSE_SCHEMA_OK_FAILED",
    "SCHEDULER_REUSE_WORLD_EPOCH_OK_FAILED",
    "SCHEDULER_REUSE_SOURCE_REAL_OK_FAILED",
    "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE",
    "SCHEDULER_LLM_REAL_PROVIDER_REQUIRED",
    "SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID",
    "SCHEDULER_FAKE_MOCK_FORBIDDEN",
    "SCHEDULER_DISPATCH_FAILED",
    "SCHEDULER_CAPABILITY_CONTRACT_INVALID",
    "SCHEDULER_CAPABILITY_UNAVAILABLE",
    "SCHEDULER_PREEMPTION_UNSUPPORTED",
    "SCHEDULER_PREEMPTION_TIMEOUT",
    "SCHEDULER_DEBUG_EXPORT_FAILED",
}


@dataclass
class SchedulerError(Exception):
    error_code: str
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.error_code not in SCHEDULER_ERROR_CODES:
            self.metadata.setdefault("unregistered_error_code", self.error_code)
        display = self.error_code if not self.message else f"{self.error_code}: {self.message}"
        super().__init__(display)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": False,
            "error_code": self.error_code,
            "message": self.message or self.error_code,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SchedulerResult:
    success: bool
    error_code: str = ""
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    data: Any = None

    @classmethod
    def ok(cls, data: Any = None, **metadata: Any) -> "SchedulerResult":
        return cls(True, metadata=dict(metadata), data=data)

    @classmethod
    def error(cls, error_code: str, message: str = "", **metadata: Any) -> "SchedulerResult":
        return cls(False, error_code=error_code, message=message or error_code, metadata=dict(metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "error_code": self.error_code,
            "message": self.message,
            "metadata": dict(self.metadata),
            "data": self.data,
        }
