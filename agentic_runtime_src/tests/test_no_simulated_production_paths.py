from __future__ import annotations

from dataclasses import replace

import pytest

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.ros_bridge_client.client import create_ros_bridge_client
from agentic_runtime.server import RuntimeServer
from agentic_runtime.simulation import SIMULATED_BACKEND_DISABLED


def test_ros_bridge_factory_has_no_mock_client_import(runtime_src):
    source = (runtime_src / "agentic_runtime" / "ros_bridge_client" / "client.py").read_text(encoding="utf-8")

    assert "MockRosBridgeClient" not in source
    assert "mock_client" not in source


def test_runtime_server_create_mock_without_explicit_bridge_is_disabled():
    with pytest.raises(RuntimeError, match=SIMULATED_BACKEND_DISABLED):
        RuntimeServer.create(mock=True)


def test_ros_bridge_factory_rejects_mock_flag_and_config():
    config = RuntimeConfig.load()
    with pytest.raises(RuntimeError, match=SIMULATED_BACKEND_DISABLED):
        create_ros_bridge_client(config, mock=True)

    simulated_config = replace(config, ros_bridge_mode="mock")
    with pytest.raises(RuntimeError, match=SIMULATED_BACKEND_DISABLED):
        create_ros_bridge_client(simulated_config)
