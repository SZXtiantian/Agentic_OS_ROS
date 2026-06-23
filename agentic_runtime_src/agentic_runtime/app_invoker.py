from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from agentic_runtime.app_result import normalize_app_invocation_result
from agentic_runtime.dispatcher.app_index import AppIndex, AppIndexEntry
from agentic_runtime.simulation import simulated_backend_disabled


class AppInvoker:
    def __init__(self, runtime: Any, app_index: AppIndex) -> None:
        self.runtime = runtime
        self.app_index = app_index

    async def run_app(
        self,
        app_id: str,
        task_input: dict[str, Any],
        *,
        parent_session_id: str,
        route_plan_id: str,
    ) -> dict[str, Any]:
        entry = self.app_index.get(app_id)
        if entry is None:
            return {"success": False, "error_code": "APP_NOT_FOUND", "reason": f"app not found: {app_id}"}
        task = dict(task_input)
        if bool(task.pop("mock", False)):
            return {
                "session_id": "",
                "app_id": app_id,
                "status": "failed",
                "result": simulated_backend_disabled("AppInvoker.run_app(task_input.mock=True)"),
            }
        task.setdefault("parent_session_id", parent_session_id)
        task.setdefault("route_plan_id", route_plan_id)
        try:
            if entry.runtime_type == "aios_agent_package":
                return normalize_app_invocation_result(
                    await self._run_aios_app(entry, task),
                    source=f"{app_id}:{entry.aios_entrypoint or 'entry:RobotPhotographerAgent'}",
                )
            return normalize_app_invocation_result(
                await self._run_legacy_app(entry, task),
                source=f"{app_id}:{entry.entrypoint or 'legacy'}",
            )
        except Exception as exc:
            return {
                "success": False,
                "error_code": "APP_INVOKER_EXCEPTION",
                "reason": str(exc),
                "app_id": app_id,
                "session_id": "",
            }

    async def _run_aios_app(self, entry: AppIndexEntry, task_input: dict[str, Any]) -> dict[str, Any]:
        module_name, class_name = _split_entrypoint(entry.aios_entrypoint or "entry:RobotPhotographerAgent")
        app_dir = Path(entry.root)
        module = _load_module(app_dir / f"{module_name}.py", f"{entry.app_id}.{module_name}.dispatch")
        cls = getattr(module, class_name)
        agent = cls(runtime=self.runtime)
        if hasattr(agent, "arun"):
            return await agent.arun(task_input)
        result = agent.run(task_input)
        return normalize_app_invocation_result(result, source=f"{entry.app_id}:{entry.aios_entrypoint or 'entry'}")

    async def _run_legacy_app(self, entry: AppIndexEntry, task_input: dict[str, Any]) -> dict[str, Any]:
        task = dict(task_input)
        return await self.runtime.scheduler.run_app(entry.app_id, **task)


def _split_entrypoint(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError(f"entrypoint must be module:object, got {value}")
    module_name, object_name = value.split(":", 1)
    return module_name, object_name


def _load_module(path: Path, module_name: str):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load app module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
