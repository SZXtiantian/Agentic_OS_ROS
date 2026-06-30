import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_os.kernel.system_call import RobotCapabilityQuery
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


def checkpoint_syscall():
    query = RobotCapabilityQuery(
        operation_type="robot.inspect_area",
        skill_name="robot.inspect_area",
        app_id="test_app",
        session_id="sess_checkpoint",
        params={"place": "lab", "timeout_s": 30},
        metadata={"permissions": FULL_PERMS, "session_id": "sess_checkpoint"},
    )
    return SimpleNamespace(
        agent_name="test_app",
        operation_type="robot.inspect_area",
        params=query.params,
        query=query,
        syscall_id="ksc_checkpoint",
    )


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


def test_human_ask_requires_access_manager_before_backend(tmp_path):
    async def run():
        executor, bridge_calls, _, _ = make_executor(tmp_path, access_manager=False)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "human.ask", {"question": "Approve?", "timeout_s": 1}, "sess")
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


def test_checkpoint_capability_uses_real_bridge_checkpoint_service(tmp_path):
    async def run():
        executor, bridge_calls, _, _ = make_executor(tmp_path)

        result = await executor.checkpoint_capability(checkpoint_syscall(), reason="operator_suspend")

        assert result.success is False
        assert result.error_code == "ROS_BRIDGE_UNAVAILABLE"
        assert bridge_calls
        assert bridge_calls[0]["command"][:4] == ["ros2", "service", "call", "/agentic/capability/checkpoint"]
        assert bridge_calls[0]["command"][4] == "agentic_msgs/srv/CheckpointCapability"
        audit = executor.audit_logger.recent(limit=1)[0]
        assert audit["skill_name"] == "robot.inspect_area"
        assert audit["status"] == "failed"
        assert audit["error_code"] == "ROS_BRIDGE_UNAVAILABLE"

    asyncio.run(run())


def test_skill_executor_passes_call_id_to_inspection_bridge_request(tmp_path):
    class InspectionBridge:
        def __init__(self):
            self.inspect_calls = []

        async def check_safety(self, skill_name, args, app_id):
            return {"allowed": True, "error_code": "", "reason": ""}

        async def inspect_area(self, place, timeout_s, request_id=""):
            self.inspect_calls.append({"place": place, "timeout_s": timeout_s, "request_id": request_id})
            return {"success": True, "summary": "inspection finished", "objects": [], "anomalies": []}

    async def run():
        executor, _, resources, _ = make_executor(tmp_path)
        bridge = InspectionBridge()
        executor.dispatcher.bridge_client = bridge

        result = await executor.execute(
            app_with_permissions(FULL_PERMS),
            "robot.inspect_area",
            {"place": "lab", "timeout_s": 2},
            "sess",
            call_id="ksc_inspect",
        )

        assert result.success is True
        assert bridge.inspect_calls == [{"place": "lab", "timeout_s": 2, "request_id": "ksc_inspect"}]
        assert resources.snapshot() == {}

    asyncio.run(run())


def test_checkpoint_capability_delegates_to_bridge_and_audits_progress(tmp_path):
    class CheckpointBridge:
        def __init__(self):
            self.calls = []

        async def checkpoint_capability(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "success": True,
                "checkpoint_id": "inspect_bridge_cp",
                "partial_result": {"visited_waypoints": ["north_hall"]},
                "completed_coverage": ["zone_north"],
            }

    async def run():
        executor, _, _, _ = make_executor(tmp_path)
        bridge = CheckpointBridge()
        executor.dispatcher.bridge_client = bridge

        result = await executor.checkpoint_capability(checkpoint_syscall(), reason="operator_suspend", node_id="inspect_node")

        assert result.success is True
        assert result.data["checkpoint_id"] == "inspect_bridge_cp"
        assert result.data["partial_result"] == {"visited_waypoints": ["north_hall"]}
        assert result.data["completed_coverage"] == ["zone_north"]
        assert bridge.calls == [
            {
                "skill_name": "robot.inspect_area",
                "args": {"place": "lab", "timeout_s": 30},
                "app_id": "test_app",
                "session_id": "sess_checkpoint",
                "syscall_id": "ksc_checkpoint",
                "metadata": {"reason": "operator_suspend", "node_id": "inspect_node"},
            }
        ]
        audit = executor.audit_logger.recent(limit=1)[0]
        assert audit["status"] == "succeeded"
        assert audit["error_code"] == ""
        assert result.audit_id

    asyncio.run(run())


def test_checkpoint_capability_rejects_malformed_bridge_checkpoint_result(tmp_path):
    class BadCheckpointBridge:
        async def checkpoint_capability(self, **kwargs):
            return {"success": "yes", "checkpoint_id": "bad"}

    async def run():
        executor, _, _, _ = make_executor(tmp_path)
        executor.dispatcher.bridge_client = BadCheckpointBridge()

        result = await executor.checkpoint_capability(checkpoint_syscall(), reason="operator_suspend")

        assert result.success is False
        assert result.error_code == "SKILL_RESULT_INVALID"
        assert "success field must be boolean" in result.reason
        audit = executor.audit_logger.recent(limit=1)[0]
        assert audit["status"] == "failed"
        assert audit["error_code"] == "SKILL_RESULT_INVALID"

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


def test_memory_remember_non_structured_backend_result_is_not_success(tmp_path):
    class NonStructuredMemoryStore:
        def remember(self, app_id, session_id, key, value):
            return None

        def recall_result(self, app_id, key):
            return {"success": False, "error_code": "MEMORY_NOT_FOUND"}

    async def run():
        executor, _, _, _ = make_executor(tmp_path)
        executor.dispatcher.memory_store = NonStructuredMemoryStore()

        result = await executor.execute(app_with_permissions(FULL_PERMS), "memory.remember", {"key": "k", "value": {"v": 1}}, "sess")

        assert result.success is False
        assert result.error_code == "MEMORY_RESULT_INVALID"
        record = executor.audit_logger.recent(limit=1)[0]
        assert record["status"] == "failed"
        assert record["error_code"] == "MEMORY_RESULT_INVALID"

    asyncio.run(run())


def test_memory_recall_backend_failure_is_not_reported_as_empty_success(tmp_path):
    class FailingMemoryStore:
        def remember(self, app_id, session_id, key, value):
            return {"success": True, "memory_id": key}

        def recall_result(self, app_id, key):
            return {"success": False, "error_code": "MEMORY_PROVIDER_UNAVAILABLE", "reason": "db closed"}

        def recall(self, app_id, key):
            return None

    async def run():
        executor, _, _, _ = make_executor(tmp_path)
        executor.dispatcher.memory_store = FailingMemoryStore()

        result = await executor.execute(app_with_permissions(FULL_PERMS), "memory.recall", {"key": "k"}, "sess")

        assert result.success is False
        assert result.error_code == "MEMORY_PROVIDER_UNAVAILABLE"
        assert "value" not in result.data
        record = executor.audit_logger.recent(limit=1)[0]
        assert record["status"] == "failed"
        assert record["error_code"] == "MEMORY_PROVIDER_UNAVAILABLE"

    asyncio.run(run())


def test_memory_recall_requires_structured_backend_result(tmp_path):
    class NonStructuredRecallMemoryStore:
        def remember(self, app_id, session_id, key, value):
            return {"success": True, "memory_id": key}

        def recall_result(self, app_id, key):
            return None

    async def run():
        executor, _, _, _ = make_executor(tmp_path)
        executor.dispatcher.memory_store = NonStructuredRecallMemoryStore()

        result = await executor.execute(app_with_permissions(FULL_PERMS), "memory.recall", {"key": "k"}, "sess")

        assert result.success is False
        assert result.error_code == "MEMORY_RESULT_INVALID"
        assert "value" not in result.data
        record = executor.audit_logger.recent(limit=1)[0]
        assert record["status"] == "failed"
        assert record["error_code"] == "MEMORY_RESULT_INVALID"

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


def test_skill_backend_success_field_must_be_boolean(tmp_path):
    async def run():
        executor, _, _, _ = make_executor(tmp_path)

        async def malformed_dispatch(*args, **kwargs):
            return {"success": "false", "message": "string success must not pass"}

        executor.dispatcher.dispatch = malformed_dispatch
        result = await executor.execute(app_with_permissions(FULL_PERMS), "report.say", {"message": "hello"}, "sess")

        assert result.success is False
        assert result.error_code == "SKILL_RESULT_INVALID"
        assert "success field must be boolean" in result.reason
        record = executor.audit_logger.recent(limit=1)[0]
        assert record["status"] == "failed"
        assert record["error_code"] == "SKILL_RESULT_INVALID"

    asyncio.run(run())


def test_skill_backend_answered_field_must_be_boolean(tmp_path):
    async def run():
        executor, _, _, _ = make_executor(tmp_path)

        async def malformed_dispatch(*args, **kwargs):
            return {"answered": "false", "answer": ""}

        executor.dispatcher.dispatch = malformed_dispatch
        result = await executor.execute(app_with_permissions(FULL_PERMS), "report.say", {"message": "hello"}, "sess")

        assert result.success is False
        assert result.error_code == "SKILL_RESULT_INVALID"
        assert "answered field must be boolean" in result.reason

    asyncio.run(run())


def test_skill_backend_failure_without_error_code_gets_stable_code(tmp_path):
    async def run():
        executor, _, _, _ = make_executor(tmp_path)

        async def failed_dispatch(*args, **kwargs):
            return {"success": False, "reason": "backend refused without code"}

        executor.dispatcher.dispatch = failed_dispatch
        result = await executor.execute(app_with_permissions(FULL_PERMS), "report.say", {"message": "hello"}, "sess")

        assert result.success is False
        assert result.error_code == "SKILL_BACKEND_FAILED"
        assert result.reason == "backend refused without code"
        record = executor.audit_logger.recent(limit=1)[0]
        assert record["status"] == "failed"
        assert record["error_code"] == "SKILL_BACKEND_FAILED"

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
