import asyncio
import json

from agentic_runtime.photo_cli import RobotPhotoCLI


def test_photo_cli_waits_for_existing_bridge_process(monkeypatch):
    cli = RobotPhotoCLI(real=True, json_output=True, allow_arm_motion=False, assume_yes=False)
    service_checks = iter([False, True])

    monkeypatch.setattr(cli, "_bridge_services_ready", lambda timeout_s: next(service_checks))
    monkeypatch.setattr(cli, "_managed_bridge_running", lambda: False)
    monkeypatch.setattr(cli, "_external_bridge_running", lambda: True)

    def fail_popen(*args, **kwargs):
        raise AssertionError("photo CLI should not start a duplicate bridge")

    monkeypatch.setattr("agentic_runtime.photo_cli.subprocess.Popen", fail_popen)

    assert cli._ensure_real_bridge_ready() is True


def test_photo_cli_parses_typed_ros_service_list_lines():
    cli = RobotPhotoCLI(real=True, json_output=True, allow_arm_motion=False, assume_yes=False)

    assert (
        cli._service_name_from_line("/agentic/perception/capture_photo [agentic_msgs/srv/CapturePhoto]")
        == "/agentic/perception/capture_photo"
    )
    assert cli._service_name_from_line("/agentic/robot/stop") == "/agentic/robot/stop"


def test_photo_cli_reports_ros_bridge_unavailable(monkeypatch, capsys):
    cli = RobotPhotoCLI(real=True, json_output=True, allow_arm_motion=False, assume_yes=False)
    monkeypatch.setattr(cli, "_ensure_real_bridge_ready", lambda: False)

    rc = asyncio.run(cli.run_text("拍一张照片"))

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["success"] is False
    assert payload["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
