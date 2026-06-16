from __future__ import annotations

from collections import OrderedDict

from .models import TaskRecord


def select_records_for_retention(
    records: list[TaskRecord],
    *,
    retain_recent_n: int,
    retain_failed_n: int,
    retain_rejected_n: int,
) -> list[TaskRecord]:
    latest_by_id: OrderedDict[str, TaskRecord] = OrderedDict()
    for record in records:
        latest_by_id[record.task_id] = record
    latest = sorted(latest_by_id.values(), key=lambda item: item.updated_at, reverse=True)

    selected: dict[str, TaskRecord] = {}
    for record in latest[:retain_recent_n]:
        selected[record.task_id] = record
    failed = [record for record in latest if record.status == "failed"]
    for record in failed[:retain_failed_n]:
        selected[record.task_id] = record
    rejected = [record for record in latest if record.status == "rejected"]
    for record in rejected[:retain_rejected_n]:
        selected[record.task_id] = record
    return sorted(selected.values(), key=lambda item: item.updated_at)
