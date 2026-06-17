from __future__ import annotations

import threading
import time

from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore
from agentic_os.kernel.scheduler import FIFOKernelScheduler, RoundRobinKernelScheduler, SchedulerLaneSpec
from agentic_os.kernel.system_call import (
    KernelSyscallStatus,
    RobotCapabilityQuery,
    SyscallExecutor,
    ToolQuery,
)


class SerialProbeManager:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self.lock = threading.Lock()

    def address_request(self, syscall):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls += 1
        time.sleep(0.03)
        with self.lock:
            self.active -= 1
        return {"success": True}


def test_robot_motion_lane_is_serial():
    store = KernelQueueStore()
    manager = SerialProbeManager()
    lane = SchedulerLaneSpec(
        "robot_motion",
        KernelQueueName.ROBOT_MOTION,
        concurrent=False,
        max_workers=1,
        manager_key="robot_motion",
    )
    scheduler = FIFOKernelScheduler(store, managers={"robot_motion": manager}, lanes=(lane,))
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    scheduler.start()
    try:
        threads = [
            threading.Thread(
                target=executor.execute_request,
                args=(
                    "agent_a",
                    RobotCapabilityQuery(operation_type="execute_skill", skill_name="robot.navigate_to"),
                ),
                kwargs={"timeout_s": 1.0},
            ),
            threading.Thread(
                target=executor.execute_request,
                args=(
                    "agent_b",
                    RobotCapabilityQuery(operation_type="execute_skill", skill_name="arm.move_named"),
                ),
                kwargs={"timeout_s": 1.0},
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1.0)
    finally:
        scheduler.stop()

    assert manager.calls == 2
    assert manager.max_active == 1


def test_robot_sensor_can_run_on_distinct_lane_from_llm():
    store = KernelQueueStore()
    sensor = SerialProbeManager()
    llm = SerialProbeManager()
    lanes = (
        SchedulerLaneSpec("robot_sensor", KernelQueueName.ROBOT_SENSOR, concurrent=True, manager_key="robot_sensor"),
        SchedulerLaneSpec("llm", KernelQueueName.LLM, concurrent=True, manager_key="llm"),
    )
    scheduler = FIFOKernelScheduler(store, managers={"robot_sensor": sensor, "llm": llm}, lanes=lanes)
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    scheduler.start()
    try:
        sensor_result = executor.execute_request(
            "agent_a",
            RobotCapabilityQuery(operation_type="execute_skill", skill_name="perception.capture_photo"),
            timeout_s=1.0,
        )
    finally:
        scheduler.stop()

    assert sensor_result.success is True
    assert sensor.calls == 1
    assert llm.calls == 0


def test_rr_scheduler_does_not_preempt_robot_motion():
    scheduler = RoundRobinKernelScheduler(KernelQueueStore(), managers={})

    assert scheduler.can_preempt_lane(KernelQueueName.ROBOT_MOTION) is False


def test_tool_syscall_stays_on_tool_lane_not_robot_motion():
    store = KernelQueueStore()
    executor = SyscallExecutor(queue_store=store)

    result = executor.execute_request(
        "agent_a",
        ToolQuery(operation_type="call_tool", params={"name": "math.add"}),
        timeout_s=0.01,
    )

    assert result.syscall.target == KernelQueueName.TOOL
    assert result.syscall.status == KernelSyscallStatus.TIMEOUT
    assert store.qsize(KernelQueueName.ROBOT_MOTION) == 0
