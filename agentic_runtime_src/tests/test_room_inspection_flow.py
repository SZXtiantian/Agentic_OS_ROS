import asyncio

from agentic_runtime.app_manager import AppManager
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server


def test_inspection_agent_happy_path():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="厨房")
        assert result["result"]["success"] is True
        assert result["result"]["inspection"]["summary"] == "厨房检查完成，未发现异常。"
        assert result["result"]["inspection"]["objects"] == []
        audits = server.executor.audit_logger.recent(limit=20)
        names = [record["skill_name"] for record in audits]
        for expected in [
            "world.resolve_place",
            "robot.get_state",
            "robot.navigate_to",
            "robot.inspect_area",
            "memory.remember",
            "report.say",
        ]:
            assert expected in names

    asyncio.run(run())


def test_camera_arm_inspection_agent_read_only_mock_path():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("camera_arm_inspection_agent", place="workspace")
        assert result["result"]["success"] is True
        assert result["result"]["motion_enabled"] is False
        assert result["result"]["observation"]["objects"] == []
        audits = server.executor.audit_logger.recent(limit=20)
        names = [record["skill_name"] for record in audits]
        for expected in [
            "robot.get_state",
            "arm.get_state",
            "perception.observe",
            "memory.remember",
            "report.say",
        ]:
            assert expected in names

    asyncio.run(run())


def test_camera_arm_inspection_agent_motion_mock_path():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("camera_arm_inspection_agent", place="workspace", move_arm=True)
        assert result["result"]["success"] is True
        assert result["result"]["arm_action"]["success"] is True
        assert result["result"]["gripper_action"]["success"] is True

    asyncio.run(run())


def test_inspection_agent_forbidden_zone():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="楼梯")
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "FORBIDDEN_ZONE"

    asyncio.run(run())


def test_legacy_room_inspection_app_still_runs():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("room_inspection_app", place="厨房")
        assert result["result"]["success"] is True

    asyncio.run(run())
