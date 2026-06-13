from __future__ import annotations

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.skill_registry import SkillRegistry

from .models import ConfigRefreshResult


class ConfigManager:
    def __init__(self, config: RuntimeConfig, registry: SkillRegistry) -> None:
        self.config = config
        self.registry = registry

    def refresh(self, active_motion: bool = False) -> ConfigRefreshResult:
        warnings: list[str] = []
        if active_motion:
            warnings.append("active robot motion detected; safety weakening is not applied")
        try:
            self.config = RuntimeConfig.load()
            self.registry = SkillRegistry(self.config.skill_root).load()
        except Exception as exc:
            return ConfigRefreshResult(False, error_code="CONFIG_REFRESH_FAILED", reason=str(exc))
        return ConfigRefreshResult(True, reloaded=["runtime", "skills", "places", "safety", "permissions"], warnings=warnings)
