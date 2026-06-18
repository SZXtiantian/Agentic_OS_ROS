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
    agent_name: str = ""
    model: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    partial_text: str = ""
    tool_state: dict[str, Any] = field(default_factory=dict)
    json_state: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    status: str = "running"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.partial_text:
            self.partial_text = self.partial_response

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
