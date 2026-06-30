from __future__ import annotations

from dataclasses import dataclass

from .models import DispatchLaneName, TaskNodeStatus
from .task_node import TaskNode


@dataclass(frozen=True)
class PriorityKey:
    safety_rank: int
    deadline_rank: int
    inherited_priority: int
    base_priority: int
    critical_path_rank: int
    opportunity_rank: int
    aging_rank: int
    environment_rank: int
    risk_rank: int
    tie_breaker: int

    def as_heap_tuple(self) -> tuple[int, ...]:
        return (
            -self.safety_rank,
            -self.deadline_rank,
            -self.inherited_priority,
            -self.base_priority,
            -self.critical_path_rank,
            -self.opportunity_rank,
            -self.aging_rank,
            -self.environment_rank,
            self.risk_rank,
            self.tie_breaker,
        )


class PriorityScorer:
    def __init__(self, agent_lifecycle=None) -> None:
        self.agent_lifecycle = agent_lifecycle

    def score(self, node: TaskNode, now_ns: int) -> PriorityKey:
        agent_priority = self._agent_priority(node.agent_id)
        node.effective_priority = max(node.base_priority + agent_priority, node.inherited_priority)
        return PriorityKey(
            safety_rank=_safety_rank(node),
            deadline_rank=_deadline_rank(node, now_ns),
            inherited_priority=node.inherited_priority,
            base_priority=node.base_priority + agent_priority,
            critical_path_rank=int(node.critical_path_rank or 0),
            opportunity_rank=10 if node.opportunistic else 0,
            aging_rank=_aging_rank(node, now_ns),
            environment_rank=len(node.consumes_facts) + len(node.produces_facts),
            risk_rank=_risk_rank(node),
            tie_breaker=node.created_ns,
        )

    def _agent_priority(self, agent_id: str) -> int:
        if not self.agent_lifecycle or not agent_id:
            return 0
        try:
            return int(self.agent_lifecycle.get_agent(agent_id).priority)
        except Exception:
            return 0


def _safety_rank(node: TaskNode) -> int:
    if node.lane == DispatchLaneName.EMERGENCY:
        return 100
    if node.lane == DispatchLaneName.SAFETY:
        return 80
    if str(node.safety_class).lower() in {"emergency", "safety"}:
        return 70
    return 10


def _deadline_rank(node: TaskNode, at_ns: int) -> int:
    if node.deadline_ns is None:
        return 0
    slack = node.deadline_ns - at_ns
    if slack <= 0:
        return 100
    return max(1, min(99, 100 - int(slack / 1_000_000_000)))


def _aging_rank(node: TaskNode, at_ns: int) -> int:
    since = node.ready_since_ns or node.created_ns
    return max(0, min(100, int((at_ns - since) / 1_000_000_000)))


def _risk_rank(node: TaskNode) -> int:
    if node.status in {TaskNodeStatus.BLOCKED, TaskNodeStatus.STALE}:
        return 80
    if node.safety_constraints:
        return 20
    return 0
