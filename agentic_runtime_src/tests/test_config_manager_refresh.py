from agentic_runtime.config_manager import ConfigManager
from agentic_runtime.server import RuntimeServer


def test_config_manager_refresh_returns_structured_result():
    server = RuntimeServer.create(mock=True)
    result = ConfigManager(server.config, server.registry).refresh()

    assert result.success is True
    assert "runtime" in result.reloaded
