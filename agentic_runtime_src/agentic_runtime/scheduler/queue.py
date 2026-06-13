from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class ScheduledItem:
    kind: str
    payload: dict[str, Any]


class SchedulerQueue:
    def __init__(self) -> None:
        self.stop_queue: deque[ScheduledItem] = deque()
        self.normal_queue: deque[ScheduledItem] = deque()

    def put(self, item: ScheduledItem, priority_stop: bool = False) -> None:
        if priority_stop:
            self.stop_queue.append(item)
        else:
            self.normal_queue.append(item)

    def get(self) -> ScheduledItem | None:
        if self.stop_queue:
            return self.stop_queue.popleft()
        if self.normal_queue:
            return self.normal_queue.popleft()
        return None
