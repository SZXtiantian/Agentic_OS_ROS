import asyncio
from pathlib import Path

import agentic_runtime
from agentic_runtime.app_manager import AppManager
from agentic_runtime.server import RuntimeServer


def test_sdk_room_flow_and_memory():
    async def run():
        server = RuntimeServer.create(mock=True)
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="厨房")
        assert result["result"]["success"] is True
        value = server.executor.dispatcher.memory_store.recall("inspection_agent", "last_inspection")
        assert value["place"] == "厨房"

    asyncio.run(run())


def test_sdk_no_forbidden_patterns():
    sdk_root = Path(agentic_runtime.__file__).resolve().parent / "sdk"
    forbidden = [
        "import " + "rclpy",
        "from " + "rclpy",
        "/" + "cmd_vel",
        "/" + "scan",
        "/" + "odom",
        "/" + "tf",
    ]
    for path in sdk_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in text
