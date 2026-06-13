import asyncio

from agentic_runtime.app_manager import AppManager
from agentic_runtime.server import RuntimeServer


def test_inspection_agent_happy_path():
    async def run():
        server = RuntimeServer.create(mock=True)
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="厨房")
        assert result["result"]["success"] is True

    asyncio.run(run())
