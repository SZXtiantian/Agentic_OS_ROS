"""AgenticOS scheduler implementations ported from AIOS."""

from .base import BaseKernelScheduler
from .admission import AdmissionController
from .audit import REQUIRED_SCHEDULER_AUDIT_EVENTS, SchedulerAudit
from .critical_path import compute_critical_path_rank, topological_sort, validate_acyclic
from .dispatch import CapabilityDispatchAdapter, DispatchLaneMapper
from .environment import EnvironmentFact, EnvironmentStore
from .errors import SchedulerError, SchedulerResult
from .fifo_scheduler import FIFOKernelScheduler
from .fusion import FusionCommitResult, FusionPlan, GoalFusionEngine, ReuseEdge
from .graph_store import TaskGraphStore
from .lanes import DEFAULT_DAG_DISPATCH_LANES, DEFAULT_SCHEDULER_LANES, SchedulerLaneSpec
from .models import DispatchLaneName, EdgeType, PreemptPolicy, QueryType, TaskGraphStatus, TaskNodeStatus
from .preconditions import Precondition, PreconditionEvaluator
from .priority import PriorityKey, PriorityScorer
from .ready_queue import ReadyQueue
from .resource_arbiter import ResourceArbiter
from .resources import ResourceLease, ResourceRequest
from .rr_scheduler import RoundRobinKernelScheduler
from .scheduler import FIFORequestScheduler, RoundRobinRequestScheduler
from .service import EnvironmentAwareDAGScheduler
from .reconstruction import (
    CriticalDeadlineProtector,
    DeadlineBudgeter,
    DynamicGraphEvent,
    FactReusePlanner,
    ImpactIndex,
    OnlineGraphReconstructor,
    StagedGraphMutation,
)
from .task_graph import TaskGraph, TypedEdge
from .task_graph_planner import TaskGraphPlanner
from .task_node import TaskNode

__all__ = [
    "BaseKernelScheduler",
    "AdmissionController",
    "CapabilityDispatchAdapter",
    "CriticalDeadlineProtector",
    "DeadlineBudgeter",
    "DispatchLaneMapper",
    "DispatchLaneName",
    "DynamicGraphEvent",
    "EdgeType",
    "EnvironmentAwareDAGScheduler",
    "EnvironmentFact",
    "EnvironmentStore",
    "DEFAULT_DAG_DISPATCH_LANES",
    "DEFAULT_SCHEDULER_LANES",
    "FIFOKernelScheduler",
    "FIFORequestScheduler",
    "FusionCommitResult",
    "FusionPlan",
    "FactReusePlanner",
    "GoalFusionEngine",
    "ImpactIndex",
    "Precondition",
    "PreconditionEvaluator",
    "PreemptPolicy",
    "OnlineGraphReconstructor",
    "PriorityKey",
    "PriorityScorer",
    "QueryType",
    "REQUIRED_SCHEDULER_AUDIT_EVENTS",
    "ReadyQueue",
    "ResourceArbiter",
    "ResourceLease",
    "ResourceRequest",
    "ReuseEdge",
    "RoundRobinKernelScheduler",
    "RoundRobinRequestScheduler",
    "SchedulerError",
    "SchedulerAudit",
    "SchedulerLaneSpec",
    "SchedulerResult",
    "StagedGraphMutation",
    "TaskGraph",
    "TaskGraphPlanner",
    "TaskGraphStatus",
    "TaskGraphStore",
    "TaskNode",
    "TaskNodeStatus",
    "TypedEdge",
    "compute_critical_path_rank",
    "topological_sort",
    "validate_acyclic",
]
