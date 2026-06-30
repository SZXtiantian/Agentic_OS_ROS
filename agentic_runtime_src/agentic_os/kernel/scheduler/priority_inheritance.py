from __future__ import annotations

from .task_node import TaskNode


def apply_priority_inheritance(holder: TaskNode, waiter: TaskNode) -> bool:
    if waiter.effective_priority <= holder.effective_priority:
        return False
    holder.inherited_priority = max(holder.inherited_priority, waiter.effective_priority)
    holder.effective_priority = max(holder.effective_priority, holder.inherited_priority)
    return True
