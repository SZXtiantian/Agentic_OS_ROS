from __future__ import annotations

from typing import Any


class KernelService:
    def __init__(self, runtime_server) -> None:
        self.runtime_server = runtime_server

    def status(self) -> dict[str, Any]:
        skills = [skill.name for skill in self.runtime_server.registry.list_skills()]
        return self.runtime_server.monitor.status(skills, ros_bridge=self.runtime_server.config.ros_bridge_mode)

    def core_status(self) -> dict[str, Any]:
        return {
            "scheduler": self.runtime_server.scheduler.status(),
            "sessions": len(self.runtime_server.session_manager.list_sessions(limit=100)),
            "bridge": self.runtime_server.bridge_manager.status(),
        }

    async def run_app(self, app_id: str, place: str = "厨房", mock: bool = True) -> dict[str, Any]:
        return await self.runtime_server.scheduler.run_app(app_id, place=place, mock=mock)
