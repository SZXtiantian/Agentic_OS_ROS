from __future__ import annotations

from .note import MemoryNote


def choose_notes_for_eviction(notes: list[MemoryNote], overflow: int, policy: str = "oldest") -> list[MemoryNote]:
    if overflow <= 0:
        return []
    if policy == "importance":
        ordered = sorted(notes, key=lambda note: (float(note.metadata.get("importance", 0.0)), note.created_at))
    else:
        ordered = sorted(notes, key=lambda note: note.created_at)
    return ordered[:overflow]
