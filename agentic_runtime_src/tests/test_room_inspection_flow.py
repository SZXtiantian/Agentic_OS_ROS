import asyncio

from agentic_runtime.app_manager import AppManager
from agentic_runtime.server import RuntimeServer


def test_inspection_agent_happy_path():
    async def run():
        server = RuntimeServer.create(mock=True)
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="厨房")
        assert result["result"]["success"] is True
        assert result["result"]["inspection"]["summary"] == "厨房检查完成，未发现异常。"
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


def test_inspection_agent_forbidden_zone():
    async def run():
        server = RuntimeServer.create(mock=True)
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="楼梯")
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "FORBIDDEN_ZONE"

    asyncio.run(run())


def test_legacy_room_inspection_app_still_runs():
    async def run():
        server = RuntimeServer.create(mock=True)
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("room_inspection_app", place="厨房")
        assert result["result"]["success"] is True

    asyncio.run(run())
