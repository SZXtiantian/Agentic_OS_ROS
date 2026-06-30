from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .priority import PriorityKey


@dataclass(order=True)
class _ReadyItem:
    heap_key: tuple[int, ...]
    version: int
    node_id: str = field(compare=False)
    priority: PriorityKey = field(compare=False)


class ReadyQueue:
    def __init__(self) -> None:
        self._heap: list[_ReadyItem] = []
        self._versions: dict[str, int] = {}
        self._removed: set[str] = set()

    def push(self, node_id: str, priority: PriorityKey) -> None:
        version = self._versions.get(node_id, 0) + 1
        self._versions[node_id] = version
        self._removed.discard(node_id)
        heapq.heappush(self._heap, _ReadyItem(priority.as_heap_tuple(), version, node_id, priority))

    def pop_best(self) -> str | None:
        while self._heap:
            item = heapq.heappop(self._heap)
            if item.node_id in self._removed:
                continue
            if self._versions.get(item.node_id) != item.version:
                continue
            self._versions.pop(item.node_id, None)
            return item.node_id
        return None

    def remove(self, node_id: str) -> None:
        self._removed.add(node_id)
        self._versions.pop(node_id, None)

    def clear(self) -> None:
        self._heap.clear()
        self._versions.clear()
        self._removed.clear()

    def __len__(self) -> int:
        return len(self.snapshot())

    def snapshot(self) -> list[dict[str, object]]:
        live: list[dict[str, object]] = []
        for item in sorted(self._heap):
            if item.node_id in self._removed or self._versions.get(item.node_id) != item.version:
                continue
            live.append({"node_id": item.node_id, "priority": item.priority.__dict__})
        return live
