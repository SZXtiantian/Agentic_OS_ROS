from __future__ import annotations

import asyncio
import json

from agentic_runtime import cli as runtime_cli
from agentic_runtime.kernel_service import server as kernel_server
from agentic_runtime.nl_cli import main as nl_cli_main
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
