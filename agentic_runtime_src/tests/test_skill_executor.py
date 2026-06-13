import asyncio

from agentic_runtime.audit import AuditLogger
from agentic_runtime.config import RuntimeConfig
from agentic_runtime.memory import SQLiteMemoryStore
from agentic_runtime.permission_manager import PermissionManager
from agentic_runtime.ros_bridge_client.mock_client import MockRosBridgeClient
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


def make_executor(tmp_path, navigation_sleep_s=0.01):
    config = RuntimeConfig.load()
    registry = SkillRegistry(config.skill_root).load()
    client = MockRosBridgeClient(config.repo_root, navigation_sleep_s=navigation_sleep_s)
    memory = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    resources = ResourceManager()
    executor = SkillExecutor(
        registry,
        PermissionManager(),
        resources,
        SkillDispatcher(client, memory),
        AuditLogger(tmp_path / "audit.jsonl"),
        CancellationManager(),
    )
    return executor, client, resources, memory


def app_with_permissions(permissions):
    return AppManifest("test_app", "0", "", "main:run", permissions, [])


def test_navigate_success(tmp_path):
    async def run():
        executor, client, _, _ = make_executor(tmp_path)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.navigate_to", {"place": "厨房", "timeout_s": 2}, "sess")
        assert result.success is True
        assert client.navigation_calls

    asyncio.run(run())


def test_navigate_permission_denied_does_not_call_backend(tmp_path):
    async def run():
        executor, client, _, _ = make_executor(tmp_path)
        result = await executor.execute(app_with_permissions(["world.read"]), "robot.navigate_to", {"place": "厨房", "timeout_s": 2}, "sess")
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert client.navigation_calls == []

    asyncio.run(run())


def test_navigate_resource_locked(tmp_path):
    async def run():
        executor, _, resources, _ = make_executor(tmp_path)
        resources.acquire("base", "other", "call")
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.navigate_to", {"place": "厨房", "timeout_s": 2}, "sess")
        assert result.success is False
        assert result.error_code == "RESOURCE_LOCKED"

    asyncio.run(run())


def test_navigate_timeout_releases_base_lock(tmp_path):
    async def run():
        executor, _, resources, _ = make_executor(tmp_path, navigation_sleep_s=5)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.navigate_to", {"place": "厨房", "timeout_s": 1}, "sess")
        assert result.success is False
        assert result.error_code == "SKILL_TIMEOUT"
        assert resources.snapshot() == {}

    asyncio.run(run())


def test_stop_robot_not_blocked_by_base_lock(tmp_path):
    async def run():
        executor, client, resources, _ = make_executor(tmp_path)
        resources.acquire("base", "other", "call")
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.stop", {"reason": "manual_stop"}, "sess")
        assert result.success is True
        assert client.stop_calls

    asyncio.run(run())


def test_inspect_area_success(tmp_path):
    async def run():
        executor, _, _, _ = make_executor(tmp_path)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.inspect_area", {"place": "厨房", "timeout_s": 2}, "sess")
        assert result.success is True
        assert result.data["summary"] == "厨房检查完成，未发现异常。"

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


def test_forbidden_zone_rejected_before_navigation(tmp_path):
    async def run():
        executor, client, _, _ = make_executor(tmp_path)
        result = await executor.execute(app_with_permissions(FULL_PERMS), "robot.navigate_to", {"place": "楼梯", "timeout_s": 2}, "sess")
        assert result.success is False
        assert result.error_code == "FORBIDDEN_ZONE"
        assert client.navigation_calls == []

    asyncio.run(run())


def test_stop_cancels_active_navigation(tmp_path):
    async def run():
        executor, _, resources, _ = make_executor(tmp_path, navigation_sleep_s=2)
        app = app_with_permissions(FULL_PERMS)
        nav_task = asyncio.create_task(executor.execute(app, "robot.navigate_to", {"place": "厨房", "timeout_s": 5}, "sess"))
        await asyncio.sleep(0.1)
        stop_result = await executor.execute(app, "robot.stop", {"reason": "manual_stop"}, "sess")
        nav_result = await nav_task
        assert stop_result.success is True
        assert nav_result.success is False
        assert nav_result.error_code == "SKILL_CANCELLED"
        assert resources.snapshot() == {}

    asyncio.run(run())
