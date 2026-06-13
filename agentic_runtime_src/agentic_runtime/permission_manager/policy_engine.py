from __future__ import annotations

from agentic_runtime.errors import PermissionDeniedError
from agentic_runtime.types import AppManifest, SkillManifest


class PermissionManager:
    def check(self, app: AppManifest, skill: SkillManifest) -> None:
        granted = set(app.permissions)
        required = set(skill.permission_requirements)
        missing = sorted(required - granted)
        if missing:
            raise PermissionDeniedError(
                f"app {app.name} missing permissions for {skill.name}: {', '.join(missing)}"
            )
