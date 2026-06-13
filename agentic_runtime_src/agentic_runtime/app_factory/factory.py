from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_runtime.app_manager import AppManager
from agentic_runtime.types import AppManifest

from .validator import AppValidator


class AppFactory:
    def __init__(self, app_root: Path, executor, validator: AppValidator | None = None) -> None:
        self.app_root = app_root
        self.manager = AppManager(app_root, executor)
        self.validator = validator or AppValidator()

    def list_apps(self) -> list[dict[str, Any]]:
        apps: list[dict[str, Any]] = []
        for manifest_path in sorted(self.app_root.glob("*/app.yaml")):
            manifest = self.manager.load_manifest(manifest_path.parent.name)
            apps.append({"app_id": manifest_path.parent.name, "name": manifest.name, "version": manifest.version})
        return apps

    def load_manifest(self, app_id: str) -> AppManifest:
        return self.manager.load_manifest(app_id)

    def validate_app(self, app_id: str) -> AppManifest:
        manifest = self.load_manifest(app_id)
        self.validator.validate(self.app_root / app_id, manifest)
        return manifest

    async def run_app(self, app_id: str, **kwargs: Any) -> dict[str, Any]:
        self.validate_app(app_id)
        return await self.manager.run_app(app_id, **kwargs)
