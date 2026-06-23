from __future__ import annotations

from dataclasses import dataclass, field


ERROR_CODES = {
    "PLACE_NOT_FOUND",
    "FORBIDDEN_ZONE",
    "ROBOT_NOT_LOCALIZED",
    "ESTOP_PRESSED",
    "PERMISSION_DENIED",
    "RESOURCE_LOCKED",
    "SCHEMA_INVALID",
    "SKILL_TIMEOUT",
    "SKILL_CANCELLED",
    "NAVIGATION_TIMEOUT",
    "NAVIGATION_REJECTED",
    "NAVIGATION_FAILED",
    "INSPECTION_FAILED",
    "SAFETY_REJECTED",
    "HUMAN_TIMEOUT",
    "BACKEND_UNAVAILABLE",
    "CONFIG_REFRESH_FAILED",
    "SESSION_NOT_FOUND",
    "SESSION_STOPPED",
    "STORAGE_PATH_INVALID",
    "TOOL_FAILED",
    "TOOL_FORBIDDEN",
    "TOOL_NOT_FOUND",
    "UNEXPECTED_ERROR",
}


@dataclass
class AgenticRuntimeError(Exception):
    code: str
    message: str
    recoverable: bool = True
    suggested_recovery: list[str] = field(default_factory=lambda: ["retry", "ask_human", "cancel"])

    def __post_init__(self) -> None:
        Exception.__init__(self, f"{self.code}: {self.message}")

    def to_dict(self) -> dict:
        return {
            "success": False,
            "error_code": self.code,
            "reason": self.message,
            "recoverable": self.recoverable,
            "suggested_recovery": list(self.suggested_recovery),
        }


class PermissionDeniedError(AgenticRuntimeError):
    def __init__(self, message: str = "permission denied", code: str = "PERMISSION_DENIED") -> None:
        super().__init__(code, message, True, ["ask_human", "cancel"])


class SafetyRejectedError(AgenticRuntimeError):
    def __init__(self, code: str = "SAFETY_REJECTED", message: str = "safety rejected") -> None:
        super().__init__(code, message, True, ["ask_human", "cancel"])


class SkillTimeoutError(AgenticRuntimeError):
    def __init__(self, message: str = "skill timed out") -> None:
        super().__init__("SKILL_TIMEOUT", message, True, ["retry", "cancel"])


class SkillExecutionError(AgenticRuntimeError):
    def __init__(self, code: str = "UNEXPECTED_ERROR", message: str = "skill execution failed") -> None:
        super().__init__(code, message, True, ["retry", "ask_human", "cancel"])


class ResourceLockedError(AgenticRuntimeError):
    def __init__(self, message: str = "resource locked") -> None:
        super().__init__("RESOURCE_LOCKED", message, True, ["retry", "cancel"])


class SchemaInvalidError(AgenticRuntimeError):
    def __init__(self, message: str = "schema invalid") -> None:
        super().__init__("SCHEMA_INVALID", message, False, ["cancel"])
