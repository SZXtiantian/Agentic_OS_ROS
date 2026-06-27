from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_os.kernel.access import AlwaysAllowTestInterventionProvider
from agentic_os.kernel.system_call import RobotCapabilityQuery, ToolQuery
from agentic_runtime.errors import ResourceLockedError
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.ros_bridge_client.cli_client import Ros2CliBridgeClient
from agentic_runtime.server import RuntimeServer
from agentic_runtime.skill_executor.resource_manager import ResourceManager
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


def _runtime_with_missing_ros2(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("AGENTIC_RUNTIME_CONFIG", str(Path(__file__).resolve().parents[1] / "configs" / "runtime.yaml"))
    calls = []

    async def missing_ros2(command, timeout_s):
        calls.append((command, timeout_s))
        raise FileNotFoundError("ros2")

    server = RuntimeServer.create(bridge_client=Ros2CliBridgeClient(runner=missing_ros2))
    return server, calls


def _start_agent(service, app_id: str, session_id: str, agent_id: str):
    agent = service.create_agent(app_id=app_id, session_id=session_id, agent_id=agent_id)
    service.start_agent(agent.agent_id)
    return agent


def test_generic_tool_cannot_bypass_robot_capability(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    service.start()
    try:
        result = service.execute_request(
            "robot_safety_app",
            ToolQuery(
                operation_type="call_tool",
                params={"name": "robot.navigate_to", "args": {"place": "kitchen"}},
                metadata={"kernel_internal": True},
            ),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"


def test_robot_skill_path_uses_access_safety_audit_and_fails_fast_without_bridge(tmp_path, monkeypatch):
    server, bridge_calls = _runtime_with_missing_ros2(tmp_path, monkeypatch)
    server.kernel_service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()

    class SpyAccessManager:
        def __init__(self, delegate) -> None:
            self.delegate = delegate
            self.calls = []

        def check(self, request):
            self.calls.append(request)
            return self.delegate.check(request)

    spy_access = SpyAccessManager(server.kernel_service.access_manager)
    server.executor.access_manager = spy_access
    agent = _start_agent(server.kernel_service, "robot_safety_app", "sess_safe_chain", "agent_safe_chain")

    async def run():
        result = await server.executor.execute(
            _robot_app(),
            "robot.navigate_to",
            {"place": "厨房", "timeout_s": 2},
            "sess_safe_chain",
            agent_id=agent.agent_id,
        )
        assert result.success is False
        assert result.error_code == "ROS_BRIDGE_UNAVAILABLE"

    asyncio.run(run())

    assert spy_access.calls
    assert spy_access.calls[0].resource.resource_type == "robot_motion"
    assert spy_access.calls[0].resource.resource_id == "robot.navigate_to"
    assert bridge_calls
    assert bridge_calls[0][0][:3] == ["ros2", "service", "call"]
    assert bridge_calls[0][0][3] == "/agentic/safety/check"
    assert server.executor.resource_manager.snapshot() == {}
    record = server.audit_logger.recent(limit=1)[0]
    assert record["skill_name"] == "robot.navigate_to"
    assert record["permission_result"] == "allowed"
    assert record["safety_result"] == "denied"
    assert record["resource_lock_result"] == "not_required"
    assert record["status"] == "rejected"
    assert record["error_code"] == "ROS_BRIDGE_UNAVAILABLE"


def test_robot_skill_motion_requires_intervention_before_bridge_call(tmp_path, monkeypatch):
    server, bridge_calls = _runtime_with_missing_ros2(tmp_path, monkeypatch)
    agent = _start_agent(server.kernel_service, "robot_safety_app", "sess_robot_intervention", "agent_robot_intervention")

    async def run():
        result = await server.executor.execute(
            _robot_app(),
            "robot.navigate_to",
            {"place": "厨房", "timeout_s": 2},
            "sess_robot_intervention",
            agent_id=agent.agent_id,
        )
        assert result.success is False
        assert result.error_code == "ACCESS_INTERVENTION_REQUIRED"

    asyncio.run(run())

    assert bridge_calls == []
    record = server.audit_logger.recent(limit=1)[0]
    assert record["skill_name"] == "robot.navigate_to"
    assert record["permission_result"] == "denied"
    assert record["safety_result"] == "not_required"
    assert record["status"] == "rejected"
    assert record["error_code"] == "ACCESS_INTERVENTION_REQUIRED"


def test_same_base_motion_lock_rejects_parallel_sessions_without_bridge_dependency():
    manager = ResourceManager()
    manager.acquire("base", "sess_a", "call_a")

    with pytest.raises(ResourceLockedError):
        manager.acquire("base", "sess_b", "call_b")

    manager.release("base", "sess_a", "call_a")
    assert manager.snapshot() == {}


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
    agent_a = _start_agent(service, "agent_a", "sess_a", "agent_a")
    agent_b = _start_agent(service, "agent_b", "sess_b", "agent_b")

    service.start()
    try:
        threads = [
            threading.Thread(
                target=service.execute_request,
                args=(
                    "agent_a",
                    RobotCapabilityQuery(
                        operation_type="execute_skill",
                        skill_name="robot.navigate_to",
                        metadata={"agent_id": agent_a.agent_id},
                    ),
                ),
                kwargs={"timeout_s": 1.0},
            ),
            threading.Thread(
                target=service.execute_request,
                args=(
                    "agent_b",
                    RobotCapabilityQuery(
                        operation_type="execute_skill",
                        skill_name="arm.move_named",
                        metadata={"agent_id": agent_b.agent_id},
                    ),
                ),
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
    server, bridge_calls = _runtime_with_missing_ros2(tmp_path, monkeypatch)

    service = server.kernel_service
    service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()
    agent = _start_agent(service, "robot_kernel_app", "sess_kernel_robot", "agent_kernel_robot")
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
                    metadata={"permissions": ["robot.move"], "agent_id": agent.agent_id},
                ),
            timeout_s=3.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "ROS_BRIDGE_UNAVAILABLE"
    assert bridge_calls
    assert any(
        record["skill_name"] == "robot.navigate_to"
        and record["session_id"] == "sess_kernel_robot"
        and record["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        for record in server.audit_logger.recent(limit=20)
    )
    assert any(
        event["event_type"] == "robot.audit" and event["metadata"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        for event in status["events"]["recent"]
    )
    assert status["bridge_client"]["last_success"] is False
    assert status["bridge_client"]["last_error"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
    assert status["bridge_client"]["last_command"][:4] == ["ros2", "service", "call", "/agentic/safety/check"]


def test_kernel_service_robot_motion_requires_intervention_before_bridge(tmp_path, monkeypatch):
    server, bridge_calls = _runtime_with_missing_ros2(tmp_path, monkeypatch)

    service = server.kernel_service
    agent = _start_agent(service, "robot_kernel_app", "sess_kernel_robot_intervention", "agent_kernel_robot_intervention")
    service.start()
    try:
        result = service.execute_request(
            "robot_kernel_app",
            RobotCapabilityQuery(
                operation_type="execute_skill",
                skill_name="robot.navigate_to",
                    params={"place": "厨房", "timeout_s": 2},
                    app_id="robot_kernel_app",
                    session_id="sess_kernel_robot_intervention",
                    metadata={"permissions": ["robot.move"], "agent_id": agent.agent_id},
                ),
            timeout_s=3.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert bridge_calls == []
    assert any(
        event["event_type"] == "robot.audit" and event["metadata"]["error_code"] == "ACCESS_INTERVENTION_REQUIRED"
        for event in status["events"]["recent"]
    )


def test_kernel_robot_backend_does_not_inject_default_permissions(tmp_path, monkeypatch):
    server, bridge_calls = _runtime_with_missing_ros2(tmp_path, monkeypatch)

    service = server.kernel_service
    agent = _start_agent(service, "robot_kernel_app", "sess_kernel_robot_denied", "agent_kernel_robot_denied")
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
                metadata={"agent_id": agent.agent_id},
            ),
            timeout_s=3.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert bridge_calls == []
    assert any(
        event["event_type"] == "robot.audit" and event["metadata"]["error_code"] == "PERMISSION_DENIED"
        for event in status["events"]["recent"]
    )
