import asyncio
import json
from dataclasses import replace

import agentic_runtime.ros_bridge_client as ros_bridge_client_pkg
from agentic_runtime.config import RuntimeConfig
from agentic_runtime.ros_bridge_client import Ros2CliBridgeClient
from agentic_runtime.ros_bridge_client.client import RosBridgeModeUnsupportedError, create_ros_bridge_client


def test_ros2_cli_bridge_client_calls_services_and_actions():
    calls = []

    async def runner(command, timeout_s):
        calls.append((command, timeout_s))
        if "/agentic/world/resolve_place" in command:
            return '{"success": true, "place": {"id": "kitchen", "name": "厨房"}}'
        if "/agentic/robot/navigate_to_place" in command:
            return '{"success": true, "error_code": "", "reason": "", "result_json": "{\\"place\\": \\"厨房\\"}"}'
        raise AssertionError(command)

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        resolved = await client.resolve_place("厨房")
        nav = await client.navigate_to("厨房", 120)
        assert resolved["place"]["id"] == "kitchen"
        assert nav["success"] is True
        assert nav["result"]["place"] == "厨房"

    asyncio.run(run())

    assert calls[0][0][:4] == ["ros2", "service", "call", "/agentic/world/resolve_place"]
    assert calls[1][0][:4] == ["ros2", "action", "send_goal", "/agentic/robot/navigate_to_place"]


def test_ros2_cli_bridge_client_parses_ros_repr_style_response():
    async def runner(command, timeout_s):
        del command, timeout_s
        return "response: agentic_msgs.srv.StopRobot_Response(success=True, error_code='', message='stop accepted')"

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        stopped = await client.stop_robot("test")
        assert stopped["success"] is True
        assert stopped["message"] == "stop accepted"

    asyncio.run(run())


def test_ros2_cli_bridge_client_parses_yaml_style_action_result():
    async def runner(command, timeout_s):
        del command, timeout_s
        return """
Waiting for an action server to become available...
Sending goal:
  place: 厨房
Goal accepted with ID: abc
Result:
  success: true
  error_code: ''
  reason: ''
  result_json: '{"place": "厨房", "mode": "nav2"}'
Goal finished with status: SUCCEEDED
"""

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        nav = await client.navigate_to("厨房", 120)
        assert nav["success"] is True
        assert nav["error_code"] == ""
        assert nav["result"]["place"] == "厨房"
        assert nav["result"]["mode"] == "nav2"

    asyncio.run(run())


def test_ros2_cli_bridge_client_parses_ros_service_nested_place():
    async def runner(command, timeout_s):
        del command, timeout_s
        return (
            "response:\n"
            "agentic_msgs.srv.ResolvePlace_Response(success=True, error_code='', reason='', "
            "place=agentic_msgs.msg.Place(id='kitchen', name='厨房', frame_id='map', "
            "pose=geometry_msgs.msg.Pose(position=geometry_msgs.msg.Point(x=3.2, y=1.5, z=0.0), "
            "orientation=geometry_msgs.msg.Quaternion(x=0.0, y=0.0, z=0.707, w=0.707)), "
            "allowed=True, metadata_json='{}'))"
        )

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        resolved = await client.resolve_place("厨房")
        assert resolved["success"] is True
        assert resolved["place"]["id"] == "kitchen"
        assert resolved["place"]["name"] == "厨房"
        assert resolved["place"]["allowed"] is True
        assert resolved["place"]["metadata"] == {}
        assert resolved["place"]["pose"]["x"] == 3.2

    asyncio.run(run())


def test_ros2_cli_bridge_client_parses_ros_service_nested_state():
    async def runner(command, timeout_s):
        del command, timeout_s
        return (
            "response:\n"
            "agentic_msgs.srv.GetRobotState_Response(success=True, error_code='', reason='', "
            "state=agentic_msgs.msg.RobotState(robot_id='real_robot', mode='real_nav2', "
            "battery_state='normal', battery_percent=87.0, is_localized=True, is_moving=False, "
            "estop_pressed=False, current_place='', active_task_id='', state_json='{\"source\": \"state_bridge_node\"}'))"
        )

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        state = await client.get_robot_state()
        assert state["success"] is True
        assert state["state"]["robot_id"] == "real_robot"
        assert state["state"]["mode"] == "real_nav2"
        assert state["state"]["battery_percent"] == 87.0
        assert state["state"]["state"]["source"] == "state_bridge_node"

    asyncio.run(run())


def test_bridge_factory_can_select_cli_without_rclpy(tmp_path):
    config = RuntimeConfig.load()
    config = replace(config, ros_bridge_mode="cli", repo_root=tmp_path)

    client = create_ros_bridge_client(config)

    assert isinstance(client, Ros2CliBridgeClient)


def test_bridge_factory_reports_stable_error_for_unimplemented_real_modes(tmp_path):
    config = replace(RuntimeConfig.load(), ros_bridge_mode="service", repo_root=tmp_path)

    try:
        create_ros_bridge_client(config)
    except RosBridgeModeUnsupportedError as exc:
        assert exc.error_code == "ROS_BRIDGE_MODE_UNSUPPORTED"
        assert exc.status["error_code"] == "ROS_BRIDGE_MODE_UNSUPPORTED"
        assert exc.status["available_modes"] == []
        assert "service" in exc.status["unsupported_modes"]
    else:
        raise AssertionError("unimplemented ROS bridge mode must not create a client")


def test_ros_bridge_package_does_not_export_mock_client():
    assert not hasattr(ros_bridge_client_pkg, "MockRosBridgeClient")


def test_ros2_cli_bridge_report_say_writes_real_report_log(tmp_path, monkeypatch, capsys):
    report_path = tmp_path / "reports" / "report.jsonl"
    monkeypatch.setenv("AGENTIC_REPORT_LOG", str(report_path))

    async def run():
        client = Ros2CliBridgeClient()
        result = await client.report_say("inspection complete")
        return result, client.status()

    result, status = asyncio.run(run())

    assert result["success"] is True
    assert result["transport"] == "file_report_sink"
    assert result["report_path"] == str(report_path)
    assert capsys.readouterr().out.strip() == "inspection complete"
    record = json.loads(report_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["message"] == "inspection complete"
    assert status["last_operation"] == "report_say"
    assert status["last_success"] is True


def test_ros2_cli_bridge_report_say_preserves_backend_failure(tmp_path, monkeypatch):
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("x", encoding="utf-8")
    report_path = blocking_file / "report.jsonl"
    monkeypatch.setenv("AGENTIC_REPORT_LOG", str(report_path))

    async def run():
        client = Ros2CliBridgeClient()
        result = await client.report_say("inspection complete")
        return result, client.status()

    result, status = asyncio.run(run())

    assert result["success"] is False
    assert result["error_code"] == "REPORT_BACKEND_UNAVAILABLE"
    assert result["report_path"] == str(report_path)
    assert status["last_operation"] == "report_say"
    assert status["last_success"] is False
    assert status["last_error"]["error_code"] == "REPORT_BACKEND_UNAVAILABLE"


def test_ros2_cli_bridge_ask_human_returns_uniform_success_shape():
    async def runner(command, timeout_s):
        del command, timeout_s
        return '{"answered": true, "answer": "yes", "reason": ""}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.ask_human("Ready?", timeout_s=1)
        assert result["success"] is True
        assert result["answered"] is True
        assert result["answer"] == "yes"
        assert result["error_code"] == ""

    asyncio.run(run())


def test_ros2_cli_bridge_ask_human_unanswered_is_not_success():
    async def runner(command, timeout_s):
        del command, timeout_s
        return '{"answered": false, "answer": "", "reason": "operator declined"}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.ask_human("Ready?", timeout_s=1)
        assert result["success"] is False
        assert result["answered"] is False
        assert result["error_code"] == "HUMAN_UNANSWERED"

    asyncio.run(run())


def test_ros2_cli_bridge_ask_human_bridge_error_has_success_false():
    async def runner(command, timeout_s):
        del command, timeout_s
        raise FileNotFoundError("ros2")

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.ask_human("Ready?", timeout_s=1)
        assert result["success"] is False
        assert result["answered"] is False
        assert result["error_code"] == "ROS_BRIDGE_UNAVAILABLE"

    asyncio.run(run())


def test_ros2_cli_bridge_client_camera_arm_methods():
    calls = []

    async def runner(command, timeout_s):
        calls.append((command, timeout_s))
        if "/agentic/perception/observe" in command:
            return (
                "response:\n"
                "agentic_msgs.srv.Observe_Response(success=True, error_code='', "
                "summary='Observed workspace', objects=[], evidence_path='/opt/agentic/var/evidence/a.json', "
                "evidence_json='{\"width\": 640, \"height\": 480}')"
            )
        if "/agentic/arm/get_state" in command:
            return (
                "response:\n"
                "agentic_msgs.srv.GetArmState_Response(success=True, error_code='', reason='', "
                "state=agentic_msgs.msg.ArmState(readiness='ready', active_action='', is_moving=False, "
                "gripper_ready=True, stop_available=False, state_json='{\"source\": \"bridge\"}'))"
            )
        if "/agentic/arm/move_named" in command:
            return '{"success": true, "error_code": "", "reason": "", "result_json": "{\\"backend_action\\": \\"camera_up\\"}"}'
        if "/agentic/gripper/set" in command:
            return '{"success": true, "error_code": "", "reason": "", "result_json": "{\\"command\\": \\"open\\"}"}'
        raise AssertionError(command)

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        observed = await client.observe("workspace", 5)
        state = await client.get_arm_state()
        arm = await client.move_arm_named("camera_up", 8)
        gripper = await client.set_gripper("open", timeout_s=5)
        assert observed["success"] is True
        assert observed["evidence"]["width"] == 640
        assert state["state"]["readiness"] == "ready"
        assert state["state"]["state"]["source"] == "bridge"
        assert arm["result"]["backend_action"] == "camera_up"
        assert gripper["result"]["command"] == "open"

    asyncio.run(run())

    assert calls[0][0][:4] == ["ros2", "service", "call", "/agentic/perception/observe"]
    assert calls[1][0][:4] == ["ros2", "service", "call", "/agentic/arm/get_state"]
    assert calls[2][0][:4] == ["ros2", "action", "send_goal", "/agentic/arm/move_named"]
    assert calls[3][0][:4] == ["ros2", "service", "call", "/agentic/gripper/set"]


def test_ros2_cli_bridge_client_capture_photo_method():
    calls = []

    async def runner(command, timeout_s):
        calls.append((command, timeout_s))
        assert "/agentic/perception/capture_photo" in command
        return (
            "response:\n"
            "agentic_msgs.srv.CapturePhoto_Response(success=True, error_code='', reason='', "
            "image_path='/opt/agentic/var/evidence/photos/p.png', "
            "metadata_path='/opt/agentic/var/evidence/photos/p.json', "
            "evidence_json='{\"width\": 640, \"height\": 400, \"encoding\": \"bgr8\"}')"
        )

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.capture_photo("workspace", "photo", 5)
        assert result["success"] is True
        assert result["image_path"].endswith("p.png")
        assert result["metadata_path"].endswith("p.json")
        assert result["evidence"]["width"] == 640

    asyncio.run(run())

    assert calls[0][0][:4] == ["ros2", "service", "call", "/agentic/perception/capture_photo"]


def test_ros2_cli_bridge_client_capture_photo_failure_is_structured():
    async def runner(command, timeout_s):
        del command, timeout_s
        return '{"success": false, "error_code": "CAMERA_UNAVAILABLE", "reason": "no frame", "image_path": "", "metadata_path": "", "evidence_json": "{}"}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.capture_photo("workspace", "photo", 5)
        assert result["success"] is False
        assert result["error_code"] == "CAMERA_UNAVAILABLE"
        assert result["image_path"] == ""

    asyncio.run(run())


def test_ros2_cli_bridge_client_detect_color_block_parses_detection_json_from_ros_repr():
    calls = []

    async def runner(command, timeout_s):
        calls.append((command, timeout_s))
        return """response:
agentic_msgs.srv.DetectColorBlock_Response(success=True, error_code='', reason='', detection_json='{"color":"red","camera_position_m":[0.1,0.2,0.3],"center_px":[320,240],"confidence":0.91}', evidence_json='{"kind":"color_block_detection","detection_id":"det_test"}')
"""

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.detect_color_block("red", "workspace", "red_block", 5)
        assert result["success"] is True
        assert result["detection"]["color"] == "red"
        assert result["detection"]["camera_position_m"] == [0.1, 0.2, 0.3]
        assert result["evidence"]["detection_id"] == "det_test"

    asyncio.run(run())

    assert calls[0][0][:4] == ["ros2", "service", "call", "/agentic/perception/detect_color_block"]


def test_ros2_cli_bridge_client_verify_held_color_block_parses_verification_json_from_ros_repr():
    calls = []

    async def runner(command, timeout_s):
        calls.append((command, timeout_s))
        return """response:
agentic_msgs.srv.VerifyHeldColorBlock_Response(success=True, error_code='', reason='', verified_held=True, verification_json='{"verified_held":true,"target_color":"red","candidate":{"center_px":[240,330]},"evidence_image_path":"/tmp/held.png"}', evidence_json='{"kind":"color_block_held_verification","verified_held":true}')
"""

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.verify_held_color_block(
            "red",
            "workspace",
            {"color": "red"},
            {"held": True},
            "red_block_held_verify",
            5,
        )
        assert result["success"] is True
        assert result["verified_held"] is True
        assert result["verification"]["target_color"] == "red"
        assert result["verification"]["candidate"]["center_px"] == [240, 330]
        assert result["evidence"]["kind"] == "color_block_held_verification"

    asyncio.run(run())

    assert calls[0][0][:4] == ["ros2", "service", "call", "/agentic/perception/verify_held_color_block"]


def test_ros2_cli_bridge_client_safety_timeout_retries_once():
    calls = []

    async def runner(command, timeout_s):
        calls.append((command, timeout_s))
        if len(calls) == 1:
            raise TimeoutError("slow discovery")
        return '{"allowed": true, "error_code": "", "reason": ""}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.check_safety("perception.observe", {"target": "workspace"}, "app")
        assert result["allowed"] is True

    asyncio.run(run())

    assert len(calls) == 2
    assert calls[0][0][:4] == ["ros2", "service", "call", "/agentic/safety/check"]
    assert calls[0][1] == 20


def test_ros2_cli_bridge_client_safety_timeout_returns_structured_error():
    async def runner(command, timeout_s):
        del command, timeout_s
        raise TimeoutError("still unavailable")

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.check_safety("perception.observe", {"target": "workspace"}, "app")
        assert result["allowed"] is False
        assert result["error_code"] == "SAFETY_BACKEND_TIMEOUT"

    asyncio.run(run())


def test_ros2_cli_bridge_client_missing_ros2_returns_stable_error():
    async def runner(command, timeout_s):
        del command, timeout_s
        raise FileNotFoundError("ros2")

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.get_robot_state()
        status = client.status()
        assert result["success"] is False
        assert result["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert result["state"] == {}
        assert status["provider"] == "ros2_cli"
        assert status["last_success"] is False
        assert status["last_error"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert status["last_command"][:4] == ["ros2", "service", "call", "/agentic/robot/get_state"]

    asyncio.run(run())


def test_ros2_cli_bridge_client_action_timeout_returns_stable_error():
    async def runner(command, timeout_s):
        del command, timeout_s
        raise TimeoutError("action server unavailable")

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.navigate_to("厨房", 1)
        assert result["success"] is False
        assert result["error_code"] == "ROS_ACTION_TIMEOUT"
        assert result["result"] == {}

    asyncio.run(run())


def test_ros2_cli_bridge_client_unparseable_response_returns_stable_error():
    async def runner(command, timeout_s):
        del command, timeout_s
        return "this is not a ROS response"

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.capture_photo("workspace", "photo", 5)
        status = client.status()
        assert result["success"] is False
        assert result["error_code"] == "ROS_RESULT_INVALID"
        assert result["image_path"] == ""
        assert status["last_success"] is False
        assert status["last_error"]["error_code"] == "ROS_RESULT_INVALID"
        assert status["last_error"]["operation"] == "capture_photo"

    asyncio.run(run())


def test_ros2_cli_bridge_client_rejects_string_success_field():
    async def runner(command, timeout_s):
        del command, timeout_s
        return '{"success": "false", "error_code": "", "reason": "", "state": {}}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.get_robot_state()
        status = client.status()
        assert result["success"] is False
        assert result["error_code"] == "ROS_RESULT_INVALID"
        assert "must be boolean" in result["reason"]
        assert status["last_success"] is False
        assert status["last_error"]["error_code"] == "ROS_RESULT_INVALID"
        assert status["last_error"]["operation"] == "get_robot_state"

    asyncio.run(run())


def test_ros2_cli_bridge_client_failure_without_error_code_is_invalid():
    async def runner(command, timeout_s):
        del command, timeout_s
        return '{"success": false, "reason": "no frame", "image_path": "", "metadata_path": "", "evidence_json": "{}"}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.capture_photo("workspace", "photo", 5)
        status = client.status()
        assert result["success"] is False
        assert result["error_code"] == "ROS_RESULT_INVALID"
        assert result["reason"] == "no frame"
        assert status["last_success"] is False
        assert status["last_error"]["error_code"] == "ROS_RESULT_INVALID"
        assert status["last_error"]["operation"] == "capture_photo"

    asyncio.run(run())


def test_ros2_cli_bridge_client_safety_rejects_string_allowed_field():
    async def runner(command, timeout_s):
        del command, timeout_s
        return '{"allowed": "false", "error_code": "", "reason": ""}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.check_safety("robot.navigate_to", {"place": "厨房"}, "app")
        status = client.status()
        assert result["allowed"] is False
        assert result["error_code"] == "ROS_RESULT_INVALID"
        assert "must be boolean" in result["reason"]
        assert status["last_success"] is False
        assert status["last_error"]["operation"] == "check_safety"

    asyncio.run(run())


def test_ros2_cli_bridge_client_safety_rejection_gets_stable_default_error():
    async def runner(command, timeout_s):
        del command, timeout_s
        return '{"allowed": false, "reason": "forbidden zone"}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.check_safety("robot.navigate_to", {"place": "楼梯"}, "app")
        status = client.status()
        assert result["allowed"] is False
        assert result["error_code"] == "SAFETY_REJECTED"
        assert result["reason"] == "forbidden zone"
        assert status["last_success"] is False
        assert status["last_error"]["error_code"] == "SAFETY_REJECTED"
        assert status["last_error"]["operation"] == "check_safety"

    asyncio.run(run())


def test_ros2_cli_bridge_client_human_rejects_string_answered_field():
    async def runner(command, timeout_s):
        del command, timeout_s
        return '{"answered": "false", "answer": "", "reason": ""}'

    async def run():
        client = Ros2CliBridgeClient(runner=runner)
        result = await client.ask_human("Ready?", timeout_s=1)
        status = client.status()
        assert result["success"] is False
        assert result["answered"] is False
        assert result["error_code"] == "ROS_RESULT_INVALID"
        assert "must be boolean" in result["reason"]
        assert status["last_success"] is False
        assert status["last_error"]["operation"] == "ask_human"

    asyncio.run(run())
