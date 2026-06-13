import asyncio
from dataclasses import replace

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.ros_bridge_client import Ros2CliBridgeClient
from agentic_runtime.ros_bridge_client.client import create_ros_bridge_client


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

    client = create_ros_bridge_client(config, mock=False)

    assert isinstance(client, Ros2CliBridgeClient)
