import asyncio
import sys
from pathlib import Path

RUNTIME_SRC = Path(__file__).resolve().parents[3] / "agentic_runtime_src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from agentic_runtime.app_manager import AppManager
from agentic_runtime.config import RuntimeConfig
from agentic_runtime.ros_bridge_client.mock_client import MockRosBridgeClient
from agentic_runtime.server import RuntimeServer


def test_room_inspection_app_happy_path():
    async def run():
        config = RuntimeConfig.load()
        server = RuntimeServer.create(mock=True, bridge_client=MockRosBridgeClient(config.repo_root))
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("room_inspection_app", place="厨房")
        assert result["result"]["success"] is True

    asyncio.run(run())
