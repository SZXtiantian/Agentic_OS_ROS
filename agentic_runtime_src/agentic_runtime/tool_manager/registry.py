from __future__ import annotations

from collections.abc import Callable
from typing import Any


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        if name.startswith("robot."):
            raise ValueError("robot capabilities cannot be registered as generic tools")
        self._handlers[name] = handler

    def get(self, name: str) -> ToolHandler | None:
        return self._handlers.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self._handlers)

    @classmethod
    def default(cls) -> "ToolRegistry":
        registry = cls()
        registry.register("echo", lambda args: {"message": args.get("message", "")})
        registry.register("format_report", lambda args: {"report": str(args.get("summary", "")).strip()})
        return registry
