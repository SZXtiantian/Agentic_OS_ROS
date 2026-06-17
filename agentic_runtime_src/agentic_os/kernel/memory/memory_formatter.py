from __future__ import annotations

from .note import MemoryNote


def format_memory(notes: list[MemoryNote] | list[dict]) -> str:
    lines: list[str] = []
    for note in notes:
        if isinstance(note, MemoryNote):
            lines.append(f"- {note.content}")
        else:
            lines.append(f"- {note.get('content', '')}")
    return "\n".join(lines)
