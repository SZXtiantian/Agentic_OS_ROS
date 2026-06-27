from __future__ import annotations

from agentic_runtime.types import AppManifest

from .human import HumanAPI
from .kernel import KernelAPI
from .llm import LLMAPI
from .manipulation import ArmAPI, GripperAPI
from .memory import MemoryAPI
from .perception import PerceptionAPI
from .report import ReportAPI
from .robot import RobotAPI
from .storage import StorageAPI
from .world import WorldAPI


class AgentContext:
    def __init__(self, executor, app_manifest: AppManifest, session_id: str, agent_id: str = "") -> None:
        self.executor = executor
        self.app_manifest = app_manifest
        self.session_id = session_id
        self.agent_id = agent_id
        self.kernel_service = getattr(executor, "kernel_service", None)
        self.kernel = KernelAPI(self)
        self.llm = LLMAPI(self)
        self.robot = RobotAPI(self)
        self.perception = PerceptionAPI(self)
        self.arm = ArmAPI(self)
        self.gripper = GripperAPI(self)
        self.world = WorldAPI(self)
        self.memory = MemoryAPI(self)
        self.storage = StorageAPI(self)
        self.human = HumanAPI(self)
        self.report = ReportAPI(self)

    async def call_skill(self, name: str, args: dict):
        try:
            return await self.executor.execute(
                self.app_manifest,
                name,
                args,
                session_id=self.session_id,
                agent_id=self.agent_id,
            )
        except TypeError as exc:
            if self.agent_id or "agent_id" not in str(exc):
                raise
            return await self.executor.execute(self.app_manifest, name, args, session_id=self.session_id)
