import asyncio

from agentic_runtime.context_manager import ContextManager
from agentic_runtime.scheduler import SessionRunner
from agentic_runtime.session import SessionManager, SessionStore
from agentic_runtime.storage import StorageManager
from runtime_test_helpers import create_test_runtime_server


def test_inspection_agent_runs_through_kernel_session_path():
    async def run():
        server = create_test_runtime_server()
        result = await server.scheduler.run_app("inspection_agent", place="厨房")
        assert result["status"] == "failed"
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"

        session = server.session_manager.get_session(result["session_id"])
        assert session is not None
        assert session.status == "failed"
        assert session.error_code == "ROS_BRIDGE_UNAVAILABLE"

        syscalls = server.session_manager.read_syscalls(result["session_id"], limit=100)
        final_skill_names = {record.get("skill_name") for record in syscalls if record.get("audit_id")}
        assert "report.say" in final_skill_names
        assert "world.resolve_place" in final_skill_names
        assert "robot.navigate_to" not in final_skill_names
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/world/resolve_place"

        context = server.context_manager.recover(result["session_id"])
        assert context is not None
        assert context.app_id == "inspection_agent"
        assert context.error_code == "ROS_BRIDGE_UNAVAILABLE"

    asyncio.run(run())


def test_session_runner_fails_invalid_app_result_contract(tmp_path):
    class InvalidAppFactory:
        async def run_app(self, app_id, **kwargs):
            return {"session_id": kwargs["session_id"], "app_id": app_id, "result": {"message": "missing"}}

    session_manager = SessionManager(SessionStore(tmp_path / "sessions"))
    runner = SessionRunner(
        InvalidAppFactory(),
        session_manager,
        StorageManager(tmp_path / "storage"),
        ContextManager(tmp_path / "context"),
    )

    async def run():
        result = await runner.run_app("invalid_agent", place="lab")
        assert result["status"] == "failed"
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "APP_RESULT_INVALID"
        assert result["result"]["metadata"]["keys"] == ["message"]

        session = session_manager.get_session(result["session_id"])
        assert session is not None
        assert session.status == "failed"
        assert session.error_code == "APP_RESULT_INVALID"

    asyncio.run(run())


def test_scheduler_rejects_simulated_task_field():
    async def run():
        server = create_test_runtime_server()
        scheduler_result = await server.scheduler.run_app("inspection_agent", place="厨房", mock=True)

        assert scheduler_result["status"] == "failed"
        assert scheduler_result["session_id"] == ""
        assert scheduler_result["result"]["success"] is False
        assert scheduler_result["result"]["error_code"] == "TASK_INPUT_FIELD_UNSUPPORTED"
        assert server.test_bridge_calls == []

    asyncio.run(run())
