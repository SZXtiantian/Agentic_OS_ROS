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


def skill_queue_name(skill_name: str) -> str:
    normalized = (skill_name or "").lower()
    if normalized.startswith("human."):
        return KernelQueueName.HUMAN
    if normalized.startswith(("robot.navigate_to", "robot.stop", "arm.", "gripper.")):
        return KernelQueueName.ROBOT_MOTION
    if normalized.startswith(("perception.", "world.")) or normalized in {"robot.get_state", "robot.inspect_area"}:
        return KernelQueueName.ROBOT_SENSOR
    if normalized.startswith("report."):
        return KernelQueueName.SKILL
    return KernelQueueName.SKILL


def robot_capability_queue_name(query: RobotCapabilityQuery) -> str:
    return skill_queue_name(query.skill_name or query.operation_type)
