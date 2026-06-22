from __future__ import annotations

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.ros_bridge_client.mock_client import MockRosBridgeClient
from agentic_runtime.server import RuntimeServer


def create_test_runtime_server(*, navigation_sleep_s: float = 0.05) -> RuntimeServer:
    config = RuntimeConfig.load()
    bridge_client = MockRosBridgeClient(config.repo_root, navigation_sleep_s=navigation_sleep_s)
    return RuntimeServer.create(mock=True, bridge_client=bridge_client)
