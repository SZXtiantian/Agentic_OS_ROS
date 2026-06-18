from __future__ import annotations

from .block import CompressedMemoryBlock
from .note import MemoryNote


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def compress_notes(agent_name: str, notes: list[MemoryNote], session_id: str = "") -> CompressedMemoryBlock:
    note_ids = [note.id for note in notes]
    fragments = [str(note.content) for note in notes if str(note.content)]
    summary = " | ".join(fragments)[:1000]
    metadata = {
        "note_metadata": [dict(note.metadata) for note in notes],
        "tags": sorted({tag for note in notes for tag in note.tags}),
        "keywords": sorted({keyword for note in notes for keyword in note.keywords}),
    }
    return CompressedMemoryBlock(
        agent_name=agent_name,
        session_id=session_id,
        notes=note_ids,
        summary=summary,
        token_estimate=estimate_tokens(summary),
        metadata=metadata,
    )
