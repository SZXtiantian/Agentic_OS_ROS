from agentic_runtime.nl_gateway import _flags_from_args, build_parser, _service_name_from_line


def test_nl_gateway_parser_defaults_to_real():
    args = build_parser().parse_args(["--json", "拍一张照片"])
    flags = _flags_from_args(args)
    assert flags.mock is False
    assert flags.real is True
    assert flags.json is True


def test_nl_gateway_parser_explicit_mock_flag():
    args = build_parser().parse_args(["--mock", "--json", "拍一张照片"])
    flags = _flags_from_args(args)
    assert flags.mock is True
    assert flags.real is False
    assert flags.json is True


def test_nl_gateway_parser_real_flags():
    args = build_parser().parse_args(["--real", "--allow-arm-motion", "--yes", "拍一组多角度照片"])
    flags = _flags_from_args(args)
    assert flags.real is True
    assert flags.mock is False
    assert flags.allow_arm_motion is True
    assert flags.assume_yes is True


def test_nl_gateway_service_line_parser():
    assert _service_name_from_line("/agentic/robot/stop [agentic_msgs/srv/StopRobot]") == "/agentic/robot/stop"
