from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any

from agentic_runtime.types import SkillManifest

from .context import SkillRuntimeContext


class PythonSkillRunner:
    async def run(self, skill: SkillManifest, args: dict[str, Any], context: SkillRuntimeContext) -> dict[str, Any]:
        entrypoint = str(skill.implementation.get("entrypoint") or "")
        if ":" not in entrypoint:
            return {
                "success": False,
                "error_code": "SKILL_BACKEND_UNAVAILABLE",
                "reason": f"python skill {skill.name} is missing implementation.entrypoint",
            }
        module_name, function_name = entrypoint.split(":", 1)
        module_path = self._module_path(skill, module_name)
        if not module_path.exists():
            return {
                "success": False,
                "error_code": "SKILL_BACKEND_UNAVAILABLE",
                "reason": f"python skill module not found: {module_path}",
            }
        spec = importlib.util.spec_from_file_location(
            f"agentic_skill_{skill.name.replace('.', '_')}_{abs(hash(str(module_path)))}",
            module_path,
        )
        if spec is None or spec.loader is None:
            return {
                "success": False,
                "error_code": "SKILL_BACKEND_UNAVAILABLE",
                "reason": f"cannot load python skill module: {module_path}",
            }
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        func = getattr(module, function_name, None)
        if not callable(func):
            return {
                "success": False,
                "error_code": "SKILL_BACKEND_UNAVAILABLE",
                "reason": f"python skill entrypoint is not callable: {entrypoint}",
            }
        result = self._call(func, args, context)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, dict) else {
            "success": False,
            "error_code": "SKILL_RESULT_INVALID",
            "reason": f"python skill returned {type(result).__name__}",
        }

    def _module_path(self, skill: SkillManifest, module_name: str) -> Path:
        source = Path(skill.source_path).expanduser()
        base = source.parent if source else Path.cwd()
        return base / f"{module_name.replace('.', '/')}.py"

    def _call(self, func, args: dict[str, Any], context: SkillRuntimeContext):
        signature = inspect.signature(func)
        parameters = signature.parameters
        if not parameters:
            return func()
        if "context" in parameters:
            return func(args, context=context)
        if "ctx" in parameters:
            return func(args, ctx=context)
        if len(parameters) >= 2:
            return func(args, context)
        return func(args)
