from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    app_id: str = ""
    session_id: str = ""


@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    reason: str = ""
    audit_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
