import asyncio

from agentic_runtime.app_manager import AppManager
from agentic_runtime.server import RuntimeServer


def test_room_inspection_app_happy_path():
    async def run():
        server = RuntimeServer.create(mock=True)
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("room_inspection_app", place="厨房")
        assert result["result"]["success"] is True

    asyncio.run(run())
