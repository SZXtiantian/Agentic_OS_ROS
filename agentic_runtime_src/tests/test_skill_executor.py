import asyncio
from pathlib import Path

import pytest

from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
from agentic_runtime.audit import AuditLogger
from agentic_runtime.config import RuntimeConfig
from agentic_runtime.errors import ResourceLockedError
from agentic_runtime.memory import SQLiteMemoryStore
from agentic_runtime.permission_manager import PermissionManager
from agentic_runtime.ros_bridge_client.cli_client import Ros2CliBridgeClient
from agentic_runtime.skill_executor.cancellation import CancellationManager
from agentic_runtime.skill_executor.dispatcher import SkillDispatcher
from agentic_runtime.skill_executor.executor import SkillExecutor
from agentic_runtime.skill_executor.resource_manager import ResourceManager
from agentic_runtime.skill_registry import SkillRegistry
from agentic_runtime.types import AppManifest


FULL_PERMS = [
    "robot.state.read",
    "robot.move",
    "robot.stop",
    "world.read",
    "perception.inspect",
    "memory.read",
    "memory.write",
    "human.ask",
    "report.say",
]


def make_executor(tmp_path, *, access_manager=True):
    config = RuntimeConfig.load(Path(__file__).resolve().parents[1] / "configs" / "runtime.yaml")
    registry = SkillRegistry(config.skill_root).load()
    bridge_calls = []

    async def missing_ros2(command, timeout_s):
        bridge_calls.append({"command": command, "timeout_s": timeout_s})
        raise FileNotFoundError("ros2")

    client = Ros2CliBridgeClient(runner=missing_ros2)
    memory = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    resources = ResourceManager()
    executor = SkillExecutor(
        registry,
        PermissionManager(),
        resources,
        SkillDispatcher(client, memory),
        AuditLogger(tmp_path / "audit.jsonl"),
        CancellationManager(),
        access_manager=AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider()) if access_manager else None,
    )
    return executor, bridge_calls, resources, memory


def app_with_permissions(permissions):
    return AppManifest("test_app", "0", "", "main:run", permissions, [])


def test_navigate_fails_fast_when_ros2_bridge_unavailable(tmp_path):
    async def run():
        executor, bridge_calls, resources, _ = make_executor(tmp_path)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.navigate_to", {"place": "厨房", "timeout_s": 2}, "sess")
        assert result.success is False
        assert result.error_code == "ROS_BRIDGE_UNAVAILABLE"
        assert bridge_calls
        assert bridge_calls[0]["command"][:3] == ["ros2", "service", "call"]
        assert bridge_calls[0]["command"][3] == "/agentic/safety/check"
        assert all("/agentic/robot/navigate_to_place" not in call["command"] for call in bridge_calls)
        assert resources.snapshot() == {}

    asyncio.run(run())


def test_navigate_permission_denied_does_not_call_backend(tmp_path):
    async def run():
        executor, bridge_calls, _, _ = make_executor(tmp_path)
        result = await executor.execute(app_with_permissions(["world.read"]), "robot.navigate_to", {"place": "厨房", "timeout_s": 2}, "sess")
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert bridge_calls == []

    asyncio.run(run())


def test_robot_motion_requires_access_manager_before_backend(tmp_path):
    async def run():
        executor, bridge_calls, _, _ = make_executor(tmp_path, access_manager=False)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.navigate_to", {"place": "厨房", "timeout_s": 2}, "sess")
        assert result.success is False
        assert result.error_code == "ACCESS_MANAGER_UNAVAILABLE"
        assert bridge_calls == []

    asyncio.run(run())


def test_resource_manager_rejects_parallel_base_lock_without_bridge_dependency():
    resources = ResourceManager()
    resources.acquire("base", "other", "call")
    with pytest.raises(ResourceLockedError):
        resources.acquire("base", "sess", "call")


def test_cancellation_manager_sets_session_event_without_robot_backend():
    async def run():
        manager = CancellationManager()
        event = manager.event_for("sess")
        assert event.is_set() is False
        manager.cancel_session("sess")
        assert event.is_set() is True
        replacement = manager.event_for("sess")
        assert replacement is not event
        assert replacement.is_set() is False

    asyncio.run(run())


def test_cancellation_manager_tracks_precise_active_calls():
    async def run():
        manager = CancellationManager()
        combined = manager.event_for("sess", "call_1")

        assert manager.active_calls() == [{"session_id": "sess", "call_id": "call_1"}]
        assert combined.is_set() is False
        assert manager.cancel_call("sess", "missing") is False
        assert manager.cancel_call("sess", "call_1") is True
        assert combined.is_set() is True
        manager.clear_call("sess", "call_1")
        assert manager.active_calls() == []

    asyncio.run(run())


def test_stop_robot_not_blocked_by_base_lock(tmp_path):
    async def run():
        executor, bridge_calls, resources, _ = make_executor(tmp_path)
        resources.acquire("base", "other", "call")
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.stop", {"reason": "manual_stop"}, "sess")
        assert result.success is False
        assert result.error_code == "ROS_BRIDGE_UNAVAILABLE"
        assert bridge_calls
        assert bridge_calls[0]["command"][:3] == ["ros2", "service", "call"]
        assert bridge_calls[0]["command"][3] == "/agentic/robot/stop"
        assert resources.snapshot() == {"base": "other:call"}

    asyncio.run(run())


def test_inspect_area_fails_fast_when_ros2_bridge_unavailable(tmp_path):
    async def run():
        executor, bridge_calls, resources, _ = make_executor(tmp_path)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.inspect_area", {"place": "厨房", "timeout_s": 2}, "sess")
        assert result.success is False
        assert result.error_code == "ROS_BRIDGE_UNAVAILABLE"
        assert bridge_calls
        assert bridge_calls[0]["command"][:3] == ["ros2", "service", "call"]
        assert bridge_calls[0]["command"][3] == "/agentic/safety/check"
        assert all("/agentic/perception/inspect_area" not in call["command"] for call in bridge_calls)
        assert resources.snapshot() == {}

    asyncio.run(run())


def test_memory_remember_recall_success(tmp_path):
    async def run():
        executor, _, _, _ = make_executor(tmp_path)
        app = app_with_permissions(FULL_PERMS)
        result = await executor.execute(app, "memory.remember", {"key": "k", "value": {"v": 1}}, "sess")
        assert result.success is True
        recall = await executor.execute(app, "memory.recall", {"key": "k"}, "sess")
        assert recall.data["value"] == {"v": 1}

    asyncio.run(run())


def test_memory_remember_backend_failure_is_not_reported_as_success(tmp_path):
    class FailingMemoryStore:
        def remember(self, app_id, session_id, key, value):
            return {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE", "reason": "db closed"}

        def recall(self, app_id, key):
            return None

    async def run():
        executor, _, _, _ = make_executor(tmp_path)
        executor.dispatcher.memory_store = FailingMemoryStore()

        result = await executor.execute(app_with_permissions(FULL_PERMS), "memory.remember", {"key": "k", "value": {"v": 1}}, "sess")

        assert result.success is False
        assert result.error_code == "MEMORY_PROVIDER_UNAVAILABLE"
        record = executor.audit_logger.recent(limit=1)[0]
        assert record["status"] == "failed"
        assert record["error_code"] == "MEMORY_PROVIDER_UNAVAILABLE"

    asyncio.run(run())


def test_skill_backend_response_must_explicitly_report_success(tmp_path):
    async def run():
        executor, _, _, _ = make_executor(tmp_path)

        async def malformed_dispatch(*args, **kwargs):
            return {"message": "missing success flag"}

        executor.dispatcher.dispatch = malformed_dispatch
        result = await executor.execute(app_with_permissions(FULL_PERMS), "report.say", {"message": "hello"}, "sess")

        assert result.success is False
        assert result.error_code == "SKILL_RESULT_INVALID"
        assert "missing success" in result.reason
        record = executor.audit_logger.recent(limit=1)[0]
        assert record["status"] == "failed"
        assert record["error_code"] == "SKILL_RESULT_INVALID"

    asyncio.run(run())


def test_forbidden_zone_requires_real_safety_backend_before_navigation(tmp_path):
    async def run():
        executor, bridge_calls, _, _ = make_executor(tmp_path)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.navigate_to", {"place": "楼梯", "timeout_s": 2}, "sess")
        assert result.success is False
        assert result.error_code == "ROS_BRIDGE_UNAVAILABLE"
        assert bridge_calls
        assert bridge_calls[0]["command"][3] == "/agentic/safety/check"
        assert all("/agentic/robot/navigate_to_place" not in call["command"] for call in bridge_calls)

    asyncio.run(run())
