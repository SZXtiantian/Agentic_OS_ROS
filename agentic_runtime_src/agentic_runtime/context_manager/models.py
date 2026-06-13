from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ContextSnapshot:
    session_id: str
    app_id: str
    task: dict[str, Any] = field(default_factory=dict)
    current_skill: str = ""
    last_report: str = ""
    error_code: str = ""
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
