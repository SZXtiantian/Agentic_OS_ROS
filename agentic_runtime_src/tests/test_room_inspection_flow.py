import asyncio

from agentic_runtime.app_manager import AppManager
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server


def test_inspection_agent_fails_when_ros_bridge_unavailable():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="厨房")
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        audits = server.executor.audit_logger.recent(limit=20)
        names = [record["skill_name"] for record in audits]
        for expected in [
            "world.resolve_place",
            "report.say",
        ]:
            assert expected in names
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/world/resolve_place"

    asyncio.run(run())


def test_camera_arm_inspection_agent_read_only_fails_when_ros_bridge_unavailable():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("camera_arm_inspection_agent", place="workspace")
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert result["result"]["motion_enabled"] is False
        audits = server.executor.audit_logger.recent(limit=20)
        names = [record["skill_name"] for record in audits]
        for expected in [
            "robot.get_state",
            "report.say",
        ]:
            assert expected in names
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/robot/get_state"

    asyncio.run(run())


def test_camera_arm_inspection_agent_motion_fails_when_ros_bridge_unavailable():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("camera_arm_inspection_agent", place="workspace", move_arm=True)
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert result["result"]["stop_result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"

    asyncio.run(run())


def test_inspection_agent_forbidden_zone():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="楼梯")
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/world/resolve_place"

    asyncio.run(run())


def test_legacy_room_inspection_app_fails_when_ros_bridge_unavailable():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("room_inspection_app", place="厨房")
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"

    asyncio.run(run())
