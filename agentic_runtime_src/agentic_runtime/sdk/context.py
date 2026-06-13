from __future__ import annotations

from agentic_runtime.types import AppManifest

from .human import HumanAPI
from .memory import MemoryAPI
from .report import ReportAPI
from .robot import RobotAPI
from .world import WorldAPI


class AgentContext:
    def __init__(self, executor, app_manifest: AppManifest, session_id: str) -> None:
        self.executor = executor
        self.app_manifest = app_manifest
        self.session_id = session_id
        self.robot = RobotAPI(self)
        self.world = WorldAPI(self)
        self.memory = MemoryAPI(self)
        self.human = HumanAPI(self)
        self.report = ReportAPI(self)

    async def call_skill(self, name: str, args: dict):
        return await self.executor.execute(self.app_manifest, name, args, session_id=self.session_id)
