from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.hooks import InMemoryKernelEventSink
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


def test_tool_manager_requires_execute_permission_when_access_managed():
    sink = InMemoryKernelEventSink()
    access = AccessManager(event_sink=sink)
    manager = ToolManager(access_manager=access, event_sink=sink)

    denied = manager.call(ToolCall(name="echo", args={"message": "hello"}, app_id="app"))
    allowed = manager.call(
        ToolCall(
            name="echo",
            args={"message": "hello"},
            app_id="app",
            permissions=("tool.execute",),
        )
    )

    assert denied.success is False
    assert denied.error_code == "ACCESS_DENIED"
    assert allowed.success is True
    assert allowed.data["message"] == "hello"
    checked = [event for event in sink.recent(limit=10) if event["event_type"] == "access.checked"]
    assert [event["metadata"]["allowed"] for event in checked] == [False, True]


def test_tool_manager_rejects_malformed_kernel_success(monkeypatch):
    manager = ToolManager()
    monkeypatch.setattr(
        manager.kernel,
        "address_request",
        lambda syscall: {"success": "true", "result": {"message": "fake success"}},
    )

    result = manager.call(ToolCall(name="echo", args={"message": "hello"}))

    assert result.success is False
    assert result.error_code == "TOOL_RESULT_INVALID"
    assert result.reason == "kernel tool result success field must be boolean"
