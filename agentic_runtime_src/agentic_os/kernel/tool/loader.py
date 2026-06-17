from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .manifest import ToolManifest


class ToolLoader:
    def __init__(self, tool_root: str | Path) -> None:
        self.tool_root = Path(tool_root).resolve()
        self.tool_root.mkdir(parents=True, exist_ok=True)

    def load(self, manifest: ToolManifest) -> Callable[[dict[str, Any]], Any]:
        module_name, function_name = self._parse_entrypoint(manifest.entrypoint)
        module_path = self._module_path(module_name)
        spec = importlib.util.spec_from_file_location(f"agentic_dynamic_tool_{uuid4().hex}", module_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"unable to load tool module: {module_name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = getattr(module, function_name, None)
        if handler is None or not callable(handler):
            raise ValueError(f"tool entrypoint not callable: {manifest.entrypoint}")
        return handler

    def _parse_entrypoint(self, entrypoint: str) -> tuple[str, str]:
        if ":" not in entrypoint:
            raise ValueError("tool entrypoint must be package.module:function")
        module_name, function_name = entrypoint.split(":", 1)
        if not module_name or not function_name:
            raise ValueError("tool entrypoint must be package.module:function")
        if any(part in {"", ".", ".."} for part in module_name.split(".")):
            raise ValueError("unsafe tool module path")
        return module_name, function_name

    def _module_path(self, module_name: str) -> Path:
        relative = Path(*module_name.split(".")).with_suffix(".py")
        module_path = (self.tool_root / relative).resolve()
        if self.tool_root not in module_path.parents and module_path != self.tool_root:
            raise ValueError("tool module outside tool root")
        if not module_path.exists() or not module_path.is_file():
            raise ValueError(f"tool module not found: {module_name}")
        return module_path
