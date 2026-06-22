from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

from agentic_os.kernel.system_call import RobotCapabilityQuery, ToolQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server
from agentic_runtime.types import AppManifest


def _robot_app(name: str = "robot_safety_app") -> AppManifest:
    return AppManifest(
        name=name,
        version="0",
        description="",
        entrypoint="main:run",
        permissions=["robot.move", "robot.stop", "perception.inspect", "arm.move.named", "gripper.control"],
        required_capabilities=[],
    )


def test_generic_tool_cannot_bypass_robot_capability(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    service.start()
    try:
        result = service.execute_request(
            "robot_safety_app",
            ToolQuery(operation_type="call_tool", params={"name": "robot.navigate_to", "args": {"place": "kitchen"}}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"


def test_robot_skill_path_uses_access_safety_resource_audit_and_bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    server = create_test_runtime_server()

    class SpyAccessManager:
        def __init__(self, delegate) -> None:
            self.delegate = delegate
            self.calls = []

        def check(self, request):
            self.calls.append(request)
            return self.delegate.check(request)

    spy_access = SpyAccessManager(server.kernel_service.access_manager)
    server.executor.access_manager = spy_access

    async def run():
        result = await server.executor.execute(
            _robot_app(),
            "robot.navigate_to",
            {"place": "厨房", "timeout_s": 2},
            "sess_safe_chain",
        )
        assert result.success is True

    asyncio.run(run())

    assert spy_access.calls
    assert spy_access.calls[0].resource.resource_type == "robot_motion"
    assert spy_access.calls[0].resource.resource_id == "robot.navigate_to"
    assert server.bridge_client.navigation_calls == [{"place": "厨房", "timeout_s": 2}]
    assert server.executor.resource_manager.snapshot() == {}
    record = server.audit_logger.recent(limit=1)[0]
    assert record["skill_name"] == "robot.navigate_to"
    assert record["permission_result"] == "allowed"
    assert record["safety_result"] == "allowed"
    assert record["resource_lock_result"] == "locked"
    assert record["status"] == "succeeded"


def test_same_base_motion_lock_prevents_parallel_bridge_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    server = create_test_runtime_server()
    server.bridge_client.navigation_sleep_s = 0.2
    app = _robot_app("parallel_motion_app")

    async def run():
        first = asyncio.create_task(
            server.executor.execute(app, "robot.navigate_to", {"place": "厨房", "timeout_s": 2}, "sess_a")
        )
        await asyncio.sleep(0.05)
        second = asyncio.create_task(
            server.executor.execute(app, "robot.navigate_to", {"place": "客厅", "timeout_s": 2}, "sess_b")
        )
        return await asyncio.gather(first, second)

    first_result, second_result = asyncio.run(run())

    assert first_result.success is True
    assert second_result.success is False
    assert second_result.error_code == "RESOURCE_LOCKED"
    assert len(server.bridge_client.navigation_calls) == 1
    assert server.executor.resource_manager.snapshot() == {}


class SerialRobotMotionManager:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self.lock = threading.Lock()

    def address_request(self, syscall):
        with self.lock:
            self.active += 1
            self.calls += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.03)
        with self.lock:
            self.active -= 1
        return {"success": True, "skill_name": getattr(syscall.query, "skill_name", "")}


def test_kernel_robot_motion_lane_is_serial(tmp_path):
    manager = SerialRobotMotionManager()
    service = KernelService(
        config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"),
        managers={"robot_motion": manager},
    )

    service.start()
    try:
        threads = [
            threading.Thread(
                target=service.execute_request,
                args=("agent_a", RobotCapabilityQuery(operation_type="execute_skill", skill_name="robot.navigate_to")),
                kwargs={"timeout_s": 1.0},
            ),
            threading.Thread(
                target=service.execute_request,
                args=("agent_b", RobotCapabilityQuery(operation_type="execute_skill", skill_name="arm.move_named")),
                kwargs={"timeout_s": 1.0},
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1.0)
    finally:
        service.stop()

    assert manager.calls == 2
    assert manager.max_active == 1


def test_kernel_service_robot_manager_uses_runtime_safe_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    server = create_test_runtime_server()

    service = server.kernel_service
    service.start()
    try:
        result = service.execute_request(
            "robot_kernel_app",
            RobotCapabilityQuery(
                operation_type="execute_skill",
                skill_name="robot.navigate_to",
                params={"place": "厨房", "timeout_s": 2},
                app_id="robot_kernel_app",
                session_id="sess_kernel_robot",
                metadata={"permissions": ["robot.move"]},
            ),
            timeout_s=3.0,
        )
    finally:
        service.stop()

    assert result.success is True
    assert server.bridge_client.navigation_calls == [{"place": "厨房", "timeout_s": 2}]
    assert any(
        record["skill_name"] == "robot.navigate_to" and record["session_id"] == "sess_kernel_robot"
        for record in server.audit_logger.recent(limit=20)
    )


def test_kernel_robot_backend_does_not_inject_default_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    server = create_test_runtime_server()

    service = server.kernel_service
    service.start()
    try:
        result = service.execute_request(
            "robot_kernel_app",
            RobotCapabilityQuery(
                operation_type="execute_skill",
                skill_name="robot.navigate_to",
                params={"place": "厨房", "timeout_s": 2},
                app_id="robot_kernel_app",
                session_id="sess_kernel_robot_denied",
            ),
            timeout_s=3.0,
        )
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert server.bridge_client.navigation_calls == []
