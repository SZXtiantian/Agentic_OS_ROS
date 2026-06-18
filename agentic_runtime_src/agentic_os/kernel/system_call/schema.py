from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import monotonic_id


@dataclass
class KernelQuery:
    operation_type: str
    params: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: monotonic_id("qry"))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMQuery(KernelQuery):
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] | None = None
    selected_llms: list[str] | None = None
    response_format: dict[str, Any] | None = None
    action_type: str = "chat"


@dataclass
class MemoryQuery(KernelQuery):
    pass


@dataclass
class StorageQuery(KernelQuery):
    pass


@dataclass
class ToolQuery(KernelQuery):
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RobotCapabilityQuery(KernelQuery):
    skill_name: str = ""
    app_id: str = ""
    session_id: str = ""


@dataclass
class KernelResponse:
    success: bool
    response_message: Any = None
    error_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, response_message: Any = None, metadata: dict[str, Any] | None = None) -> "KernelResponse":
        return cls(True, response_message=response_message, metadata=dict(metadata or {}))

    @classmethod
    def error(
        cls,
        error_code: str,
        response_message: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> "KernelResponse":
        return cls(False, response_message=response_message, error_code=error_code, metadata=dict(metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "response_message": self.response_message,
            "error_code": self.error_code,
            "metadata": self.metadata,
        }
