from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from agentic_runtime import cli as runtime_cli
from agentic_runtime.kernel_service import server as kernel_server
from agentic_runtime.nl_cli import AgenticNaturalLanguageCLI, main as nl_cli_main
from agentic_runtime.nl_gateway import GatewayFlags, dispatch_text
from agentic_runtime.photo_cli import RobotPhotoCLI, main as photo_cli_main
from agentic_runtime.simulation import SIMULATED_BACKEND_DISABLED


def _last_json(captured: str) -> dict:
    return json.loads(captured)


def test_runtime_cli_mock_flag_is_rejected(capsys):
    rc = runtime_cli.main(["status", "--mock", "--json"])

    payload = _last_json(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == SIMULATED_BACKEND_DISABLED


def test_runtime_cli_status_json_exposes_kernel_bridge_health(monkeypatch, capsys):
    class KernelService:
        def status(self):
            return {
                "runtime": {"agenticd": "running", "ros_bridge": "cli", "skills": [], "resource_locks": {}, "recent_syscalls": []},
                "scheduler": {"active": False, "lanes": ["llm", "memory"]},
                "bridge_client": {
                    "state": "unavailable",
                    "provider": "Ros2CliBridgeClient",
                    "error_code": "ROS_BRIDGE_UNAVAILABLE",
                    "reason": "ros2 command is unavailable",
                },
                "events": {"recent": [{"event_type": "ros_bridge.status"}]},
                "recent_syscalls": [],
            }

    monkeypatch.setattr(runtime_cli.RuntimeServer, "create", staticmethod(lambda mock=False: SimpleNamespace(kernel_service=KernelService())))

    rc = runtime_cli.main(["status", "--json"])

    payload = _last_json(capsys.readouterr().out)
    assert rc == 0
    assert payload["bridge_client"]["provider"] == "Ros2CliBridgeClient"
    assert payload["bridge_client"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
    assert payload["events"]["recent"][0]["event_type"] == "ros_bridge.status"


def test_kernel_service_server_mock_flag_is_rejected(capsys):
    rc = kernel_server.main(["--mock"])

    payload = _last_json(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == SIMULATED_BACKEND_DISABLED


def test_nl_gateway_mock_flag_is_rejected_without_runtime():
    async def run():
        return await dispatch_text("拍一张照片", GatewayFlags(mock=True, real=False, json=True))

    result = asyncio.run(run())

    assert result["success"] is False
    assert result["error_code"] == SIMULATED_BACKEND_DISABLED


def test_photo_cli_mock_flag_is_rejected(capsys):
    rc = photo_cli_main(["--mock", "--json", "拍一张照片"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == SIMULATED_BACKEND_DISABLED


def test_photo_cli_mock_runtime_is_rejected(capsys):
    cli = RobotPhotoCLI(real=False, json_output=True, allow_arm_motion=False, assume_yes=False)

    rc = asyncio.run(cli.run_text("拍一张照片"))

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == SIMULATED_BACKEND_DISABLED


def test_nl_cli_mock_flag_is_rejected(capsys):
    rc = nl_cli_main(["--mock", "--json", "看一下工作区"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == SIMULATED_BACKEND_DISABLED


def test_nl_cli_reports_ros_bridge_unavailable(monkeypatch, capsys):
    cli = AgenticNaturalLanguageCLI(real=True, json_output=True, allow_arm_motion=False)
    monkeypatch.setattr(cli, "_ensure_real_bridge_ready", lambda: False)

    rc = asyncio.run(cli.run_text("看一下工作区"))

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
