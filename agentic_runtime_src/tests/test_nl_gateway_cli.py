import asyncio

import pytest

from agentic_runtime import nl_gateway
from agentic_runtime.nl_gateway import GatewayFlags, _flags_from_args, build_parser, _service_name_from_line


def test_nl_gateway_parser_defaults_to_real():
    args = build_parser().parse_args(["--json", "拍一张照片"])
    flags = _flags_from_args(args)
    assert flags.real is True
    assert flags.json is True


def test_nl_gateway_parser_does_not_expose_mock_flag():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--mock", "--json", "拍一张照片"])
    assert exc.value.code == 2


def test_nl_gateway_parser_real_flags():
    args = build_parser().parse_args(["--real", "--allow-arm-motion", "--yes", "拍一组多角度照片"])
    flags = _flags_from_args(args)
    assert flags.real is True
    assert flags.allow_arm_motion is True
    assert flags.assume_yes is True


def test_nl_gateway_service_line_parser():
    assert _service_name_from_line("/agentic/robot/stop [agentic_msgs/srv/StopRobot]") == "/agentic/robot/stop"


def test_nl_gateway_reports_ros_bridge_unavailable(monkeypatch):
    monkeypatch.setattr(nl_gateway, "_ensure_real_bridge_ready", lambda flags: False)

    result = asyncio.run(nl_gateway.dispatch_text("拍一张照片", GatewayFlags(json=True)))

    assert result["success"] is False
    assert result["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
