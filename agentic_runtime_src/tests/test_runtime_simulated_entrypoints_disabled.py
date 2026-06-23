from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agentic_runtime import cli as runtime_cli
from agentic_runtime.kernel_service import server as kernel_server
from agentic_runtime.nl_cli import AgenticNaturalLanguageCLI, main as nl_cli_main
from agentic_runtime.nl_gateway import build_parser as build_gateway_parser
from agentic_runtime.photo_cli import RobotPhotoCLI, main as photo_cli_main


def _last_json(captured: str) -> dict:
    return json.loads(captured)


def test_runtime_cli_mock_flag_is_not_exposed():
    with pytest.raises(SystemExit) as exc:
        runtime_cli.main(["status", "--mock", "--json"])
    assert exc.value.code == 2


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

    monkeypatch.setattr(runtime_cli.RuntimeServer, "create", staticmethod(lambda: SimpleNamespace(kernel_service=KernelService())))

    rc = runtime_cli.main(["status", "--json"])

    payload = _last_json(capsys.readouterr().out)
    assert rc == 0
    assert payload["bridge_client"]["provider"] == "Ros2CliBridgeClient"
    assert payload["bridge_client"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
    assert payload["events"]["recent"][0]["event_type"] == "ros_bridge.status"


def test_runtime_cli_run_app_does_not_forward_mock_default(monkeypatch, capsys):
    class Scheduler:
        async def run_app(self, app_id, **kwargs):
            return {
                "session_id": "sess_real",
                "app_id": app_id,
                "status": "completed",
                "result": {"success": True, "kwargs": kwargs},
            }

    monkeypatch.setattr(runtime_cli.RuntimeServer, "create", staticmethod(lambda: SimpleNamespace(scheduler=Scheduler())))

    rc = runtime_cli.main(["run-app", "inspection_agent", "--json"])

    payload = _last_json(capsys.readouterr().out)
    assert rc == 0
    assert payload["result"]["kwargs"] == {"place": "厨房"}
    assert "mock" not in payload["result"]["kwargs"]


def test_kernel_service_server_mock_flag_is_not_exposed():
    with pytest.raises(SystemExit) as exc:
        kernel_server.main(["--mock"])
    assert exc.value.code == 2


def test_nl_gateway_mock_flag_is_not_exposed():
    with pytest.raises(SystemExit) as exc:
        build_gateway_parser().parse_args(["--mock", "--json", "拍一张照片"])
    assert exc.value.code == 2


def test_photo_cli_mock_flag_is_not_exposed():
    with pytest.raises(SystemExit) as exc:
        photo_cli_main(["--mock", "--json", "拍一张照片"])
    assert exc.value.code == 2


def test_photo_cli_reports_real_bridge_unavailable(monkeypatch, capsys):
    cli = RobotPhotoCLI(json_output=True, allow_arm_motion=False, assume_yes=False)
    monkeypatch.setattr(cli, "_ensure_real_bridge_ready", lambda: False)

    rc = asyncio.run(cli.run_text("拍一张照片"))

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == "ROS_BRIDGE_UNAVAILABLE"


def test_nl_cli_mock_flag_is_not_exposed():
    with pytest.raises(SystemExit) as exc:
        nl_cli_main(["--mock", "--json", "看一下工作区"])
    assert exc.value.code == 2


def test_nl_cli_reports_ros_bridge_unavailable(monkeypatch, capsys):
    cli = AgenticNaturalLanguageCLI(json_output=True, allow_arm_motion=False)
    monkeypatch.setattr(cli, "_ensure_real_bridge_ready", lambda: False)

    rc = asyncio.run(cli.run_text("看一下工作区"))

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
