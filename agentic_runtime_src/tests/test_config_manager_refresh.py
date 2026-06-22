from agentic_runtime.config_manager import ConfigManager
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server


def test_config_manager_refresh_returns_structured_result():
    server = create_test_runtime_server()
    result = ConfigManager(server.config, server.registry).refresh()

    assert result.success is True
    assert "runtime" in result.reloaded
