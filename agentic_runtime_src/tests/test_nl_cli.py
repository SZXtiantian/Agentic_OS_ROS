from agentic_runtime.nl_cli import parse_natural_language


def test_parse_camera_observation_chinese_command():
    intent = parse_natural_language("看一下工作区")

    assert intent.action == "camera_arm_inspection"
    assert intent.place == "workspace"
    assert intent.move_arm is False


def test_parse_camera_observation_english_place():
    intent = parse_natural_language("take a photo target=workspace")

    assert intent.action == "camera_arm_inspection"
    assert intent.place == "workspace"


def test_parse_arm_motion_request_is_separate_from_permission():
    intent = parse_natural_language("把相机抬起看一下工作区")

    assert intent.action == "camera_arm_inspection"
    assert intent.move_arm is True


def test_parse_operational_commands():
    assert parse_natural_language("查看状态").action == "status"
    assert parse_natural_language("最近会话").action == "sessions"
    assert parse_natural_language("最近审计").action == "audit"
    assert parse_natural_language("停止机器人").action == "stop"
    assert parse_natural_language("退出").action == "exit"
