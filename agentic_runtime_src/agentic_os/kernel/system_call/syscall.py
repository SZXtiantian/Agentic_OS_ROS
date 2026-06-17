from __future__ import annotations

from agentic_os.kernel.hooks import KernelQueueName

from .models import KernelSyscall
from .schema import KernelQuery, RobotCapabilityQuery


class BaseKernelSyscall(KernelSyscall):
    def __init__(self, agent_name: str, query: KernelQuery, target: str, queue_name: str) -> None:
        super().__init__(
            agent_name=agent_name,
            target=target,
            operation_type=query.operation_type,
            params=dict(query.params),
            source=agent_name,
        )
        self.query = query
        self.queue_name = queue_name


def robot_capability_queue_name(query: RobotCapabilityQuery) -> str:
    skill_name = (query.skill_name or query.operation_type).lower()
    if skill_name.startswith("human."):
        return KernelQueueName.HUMAN
    if skill_name.startswith("perception.") or skill_name in {"robot.get_state", "robot.inspect_area"}:
        return KernelQueueName.ROBOT_SENSOR
    return KernelQueueName.ROBOT_MOTION
