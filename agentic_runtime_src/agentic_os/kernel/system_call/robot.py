from __future__ import annotations

from .schema import RobotCapabilityQuery
from .syscall import BaseKernelSyscall, robot_capability_queue_name


class RobotCapabilitySyscall(BaseKernelSyscall):
    def __init__(self, agent_name: str, query: RobotCapabilityQuery) -> None:
        queue_name = robot_capability_queue_name(query)
        super().__init__(agent_name, query, target=queue_name, queue_name=queue_name)


SkillSyscall = RobotCapabilitySyscall
