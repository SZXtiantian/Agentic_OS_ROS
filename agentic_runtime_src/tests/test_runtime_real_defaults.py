from __future__ import annotations

import pytest

from agentic_runtime.cli import build_parser as build_runtime_parser
from agentic_runtime.config import RuntimeConfig
from agentic_runtime.execution_monitor import ExecutionMonitor
from agentic_runtime.kernel_service.schemas import RunAppRequest
from agentic_runtime.nl_gateway import GatewayFlags, _flags_from_args, build_parser as build_gateway_parser
from agentic_runtime.photo_cli import build_parser as build_photo_parser
from agentic_runtime.ros_bridge_client.cli_client import Ros2CliBridgeClient
from agentic_runtime.ros_bridge_client.client import create_ros_bridge_client
from agentic_runtime.server import RuntimeServer
from agentic_runtime.simulation import SIMULATED_BACKEND_DISABLED
from agentic_runtime.session.models import SessionRecord


def test_runtime_server_create_defaults_to_real_cli_bridge():
    server = RuntimeServer.create()

    assert not hasattr(server.config, "allow_mock_backends")
    assert server.config.ros_bridge_mode == "cli"
    assert isinstance(server.bridge_client, Ros2CliBridgeClient)


def test_installed_agentic_yaml_disables_simulated_defaults(runtime_src):
    config = RuntimeConfig.load(runtime_src / "configs" / "agentic.yaml")

    assert not hasattr(config, "allow_mock_backends")
    assert config.ros_bridge_mode == "cli"


def test_bridge_factory_defaults_to_cli_client():
    client = create_ros_bridge_client(RuntimeConfig.load())

    assert isinstance(client, Ros2CliBridgeClient)


def test_bridge_factory_rejects_simulated_mode():
    with pytest.raises(RuntimeError, match=SIMULATED_BACKEND_DISABLED):
        create_ros_bridge_client(RuntimeConfig.load(), mock=True)


def test_runtime_server_create_rejects_simulated_mode_even_with_explicit_bridge():
    with pytest.raises(RuntimeError, match=SIMULATED_BACKEND_DISABLED):
        RuntimeServer.create(mock=True)
    with pytest.raises(RuntimeError, match=SIMULATED_BACKEND_DISABLED):
        RuntimeServer.create(mock=True, bridge_client=object())


def test_session_and_kernel_request_defaults_are_real():
    session = SessionRecord.create("app_a")
    request = RunAppRequest()

    assert "mock" not in session.to_dict()
    assert request.mock is False


def test_execution_monitor_defaults_to_real_bridge_label():
    class Audit:
        def recent(self, limit):
            return []

    class Resources:
        def snapshot(self):
            return {}

    status = ExecutionMonitor(Audit(), Resources()).status([])

    assert status["ros_bridge"] == "cli"


def test_runtime_cli_defaults_do_not_request_mock():
    parser = build_runtime_parser()

    assert parser.parse_args(["status"]).mock is False
    assert parser.parse_args(["run-app", "inspection_agent"]).mock is False


def test_natural_language_gateway_defaults_to_real_mode():
    args = build_gateway_parser().parse_args(["看一下工作区"])
    flags = _flags_from_args(args)

    assert GatewayFlags().real is True
    assert GatewayFlags().mock is False
    assert flags.real is True
    assert flags.mock is False


def test_photo_cli_defaults_to_real_mode():
    args = build_photo_parser().parse_args(["拍一张照片"])

    real = bool(not args.mock)

    assert real is True
