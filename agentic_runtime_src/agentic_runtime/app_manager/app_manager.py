from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from agentic_runtime.app_result import validate_app_result_payload
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest, new_id


class AppManager:
    def __init__(self, app_root: Path, executor) -> None:
        self.app_root = app_root
        self.executor = executor

    def load_manifest(self, app_id: str) -> AppManifest:
        path = self.app_root / app_id / "app.yaml"
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return AppManifest.from_dict(data)

    async def run_app(self, app_id: str, **kwargs: Any) -> dict[str, Any]:
        app_dir = self.app_root / app_id
        manifest = self.load_manifest(app_id)
        registry = getattr(self.executor, "registry", None)
        if registry is not None and hasattr(registry, "load_app_skills"):
            registry.load_app_skills(app_id, app_dir)
        module_name, function_name = manifest.entrypoint.split(":", 1)
        module_path = app_dir / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(f"{app_id}.{module_name}", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load app entrypoint: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        run = getattr(module, function_name)
        session_id = kwargs.pop("session_id", new_id("sess"))
        agent_id = str(kwargs.pop("agent_id", ""))
        owns_agent_lifecycle = False
        kernel_service = getattr(self.executor, "kernel_service", None)
        if not agent_id and kernel_service is not None and hasattr(kernel_service, "agent_lifecycle"):
            agent = kernel_service.agent_lifecycle.create_agent_for_session(
                app_id=app_id,
                session_id=session_id,
                agent_name=app_id,
                metadata={"created_by": "app_manager"},
            )
            agent_id = agent.agent_id
            kernel_service.agent_lifecycle.start_agent(agent_id, reason="app_manager_started")
            owns_agent_lifecycle = True
        ctx = AgentContext(executor=self.executor, app_manifest=manifest, session_id=session_id, agent_id=agent_id)
        try:
            result, _ = validate_app_result_payload(
                await run(ctx, **kwargs),
                source=f"{app_id}:{manifest.entrypoint}",
            )
            if owns_agent_lifecycle:
                if result.get("success"):
                    kernel_service.agent_lifecycle.exit_agent(agent_id, reason="app_completed", exit_code=0)
                else:
                    kernel_service.agent_lifecycle.fail_agent(
                        agent_id,
                        reason=str(result.get("reason") or "app_failed"),
                        error_code=str(result.get("error_code") or "APP_RESULT_INVALID"),
                        exit_code=1,
                    )
            return {"session_id": session_id, "agent_id": agent_id, "app_id": app_id, "result": result}
        except Exception as exc:
            if owns_agent_lifecycle:
                kernel_service.agent_lifecycle.crash_agent(agent_id, reason=str(exc), error_code="APP_EXCEPTION")
            raise
