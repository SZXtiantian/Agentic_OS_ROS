import asyncio

from agentic_runtime.server import RuntimeServer
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


def test_scheduler_and_kernel_service_reject_mock_run_app_flag():
    async def run():
        server = create_test_runtime_server()
        scheduler_result = await server.scheduler.run_app("inspection_agent", place="厨房", mock=True)
        kernel_result = await server.kernel_service.run_app("inspection_agent", place="厨房", mock=True)

        for result in [scheduler_result, kernel_result]:
            assert result["status"] == "failed"
            assert result["session_id"] == ""
            assert result["result"]["success"] is False
            assert result["result"]["error_code"] == "SIMULATED_BACKEND_DISABLED"
        assert server.test_bridge_calls == []

    asyncio.run(run())
