from __future__ import annotations

from .schema import SkillQuery
from .syscall import BaseKernelSyscall, skill_queue_name


class SkillSyscall(BaseKernelSyscall):
    def __init__(self, agent_name: str, query: SkillQuery) -> None:
        queue_name = skill_queue_name(query.skill_name or query.operation_type)
        super().__init__(agent_name, query, target=queue_name, queue_name=queue_name)
