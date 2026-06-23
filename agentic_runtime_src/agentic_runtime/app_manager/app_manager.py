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
        module_name, function_name = manifest.entrypoint.split(":", 1)
        module_path = app_dir / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(f"{app_id}.{module_name}", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load app entrypoint: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        run = getattr(module, function_name)
        session_id = kwargs.pop("session_id", new_id("sess"))
        ctx = AgentContext(executor=self.executor, app_manifest=manifest, session_id=session_id)
        result, _ = validate_app_result_payload(
            await run(ctx, **kwargs),
            source=f"{app_id}:{manifest.entrypoint}",
        )
        return {"session_id": session_id, "app_id": app_id, "result": result}
