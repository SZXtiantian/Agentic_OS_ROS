from __future__ import annotations

import inspect

from agentic_os.kernel.capability import RobotCapabilityManager
from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore
from agentic_os.kernel.human import HumanInteractionManager
from agentic_os.kernel.memory import MemoryManager
from agentic_os.kernel.scheduler import FIFOKernelScheduler, SchedulerLaneSpec
from agentic_os.kernel.storage import StorageManager
from agentic_os.kernel.system_call import (
    KernelRequestHandler,
    KernelSyscallStatus,
    MemoryQuery,
    RobotCapabilityQuery,
    SyscallExecutor,
    create_syscall,
)
from agentic_os.kernel.tool import ToolManager


def test_all_core_managers_expose_address_request(tmp_path):
    managers = [
        MemoryManager(),
        StorageManager(tmp_path / "storage"),
        ToolManager(),
        RobotCapabilityManager(),
        HumanInteractionManager(),
    ]

    for manager in managers:
        assert isinstance(manager, KernelRequestHandler)
        assert callable(manager.address_request)


def test_scheduler_accepts_protocol_managers():
    store = KernelQueueStore()
    memory = MemoryManager()
    lane = SchedulerLaneSpec("memory", "memory", concurrent=True, manager_key="memory")
    scheduler = FIFOKernelScheduler(store, managers={"memory": memory}, lanes=(lane,))
    executor = SyscallExecutor(queue_store=store)

    scheduler.start()
    try:
        result = executor.execute_request(
            "agent_a",
            MemoryQuery(operation_type="remember", params={"memory_id": "x", "content": "hello"}),
            timeout_s=1.0,
        )
    finally:
        scheduler.stop()

    assert result.success is True
    assert result.syscall.status == KernelSyscallStatus.DONE


def test_robot_manager_does_not_import_rclpy():
    import agentic_os.kernel.capability.manager as robot_manager_module

    source = inspect.getsource(robot_manager_module)

    assert "rclpy" not in source


def test_robot_manager_returns_not_wired_without_skill_adapter():
    manager = RobotCapabilityManager()
    request = RobotCapabilityQuery(operation_type="execute_skill", skill_name="robot.navigate_to")
    created = create_syscall("agent_a", request)

    result = manager.address_request(created)

    assert result["success"] is False
    assert result["error_code"] == "ROBOT_MANAGER_NOT_WIRED"


def test_robot_manager_rejects_malformed_backend_result():
    class Backend:
        def execute_capability(self, syscall):
            return {"message": "missing success"}

    sink = InMemoryKernelEventSink()
    manager = RobotCapabilityManager(Backend(), event_sink=sink)
    request = RobotCapabilityQuery(operation_type="execute_skill", skill_name="robot.navigate_to")
    created = create_syscall("agent_a", request)

    result = manager.address_request(created)

    assert result["success"] is False
    assert result["error_code"] == "ROBOT_RESULT_INVALID"
    assert result["skill_name"] == "robot.navigate_to"
    audit = [event for event in sink.recent(limit=5) if event["event_type"] == "robot.audit"][-1]
    assert audit["metadata"]["error_code"] == "ROBOT_RESULT_INVALID"


def test_robot_manager_rejects_non_object_backend_result():
    class Backend:
        def execute_capability(self, syscall):
            return "ok"

    manager = RobotCapabilityManager(Backend())
    request = RobotCapabilityQuery(operation_type="execute_skill", skill_name="robot.navigate_to")
    created = create_syscall("agent_a", request)

    result = manager.address_request(created)

    assert result["success"] is False
    assert result["error_code"] == "ROBOT_RESULT_INVALID"


def test_human_manager_returns_not_wired_without_adapter():
    manager = HumanInteractionManager()
    syscall = SyscallExecutor().create_syscall("agent_a", "human", "human.ask", {"question": "Ready?"})

    result = manager.address_request(syscall)

    assert result["success"] is False
    assert result["error_code"] == "HUMAN_BACKEND_UNAVAILABLE"
