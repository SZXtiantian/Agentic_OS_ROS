from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .manager import utc_now


@dataclass
class GenerationSnapshot:
    generation_id: str
    syscall_id: str
    prompt_hash: str
    partial_response: str
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GenerationContextManager(Protocol):
    def save(
        self,
        generation_id: str,
        syscall_id: str,
        prompt: Any,
        partial_response: str,
        metadata: dict[str, Any] | None = None,
    ) -> GenerationSnapshot:
        ...

    def restore(self, generation_id: str) -> GenerationSnapshot | None:
        ...
