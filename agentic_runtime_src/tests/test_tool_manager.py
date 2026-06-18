from agentic_runtime.tool_manager import ToolCall, ToolManager


def test_tool_manager_runs_allowlisted_tool():
    result = ToolManager().call(ToolCall(name="echo", args={"message": "hello"}))
    assert result.success is True
    assert result.data["message"] == "hello"


def test_tool_manager_rejects_robot_tool_backdoor():
    result = ToolManager().call(ToolCall(name="robot.navigate_to", args={"place": "厨房"}))
    assert result.success is False
    assert result.error_code == "TOOL_FORBIDDEN"


def test_tool_manager_rejects_cmd_vel_backdoor():
    result = ToolManager().call(ToolCall(name="/cmd_vel", args={"linear": 1.0}))
    assert result.success is False
    assert result.error_code == "TOOL_FORBIDDEN"
