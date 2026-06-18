from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from .note import utc_now


@dataclass
class CompressedMemoryBlock:
    agent_name: str
    session_id: str = ""
    notes: list[str] = field(default_factory=list)
    summary: str = ""
    token_estimate: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    block_id: str = field(default_factory=lambda: f"mblk_{uuid4().hex}")
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    storage_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
