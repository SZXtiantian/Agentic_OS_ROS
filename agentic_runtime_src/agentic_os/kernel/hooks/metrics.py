from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueueMetricsSnapshot:
    queues: dict[str, int] = field(default_factory=dict)

    @property
    def total_depth(self) -> int:
        return sum(self.queues.values())
