import asyncio

from agentic_runtime.app_manager import AppManager
from runtime_test_helpers import create_test_runtime_server


def test_removed_inspection_apps_are_not_registered():
    server = create_test_runtime_server()
    apps = {record["app_id"] for record in server.app_factory.list_apps()}

    assert {"app_template", "hello_world_agent", "color_block_grasper_agent", "robot_photographer_agent"} <= apps
    assert "inspection_agent" not in apps
    assert "camera_arm_inspection_agent" not in apps
    assert "room_inspection_app" not in apps


def test_app_template_runs_without_ros_bridge_dependency():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("app_template", message="catalog smoke")

        assert result["result"]["success"] is True
        audits = server.executor.audit_logger.recent(limit=20)
        assert "report.say" in [record["skill_name"] for record in audits]
        assert server.test_bridge_calls == []

    asyncio.run(run())
