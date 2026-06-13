import asyncio

from agentic_runtime.server import RuntimeServer


def test_inspection_agent_runs_through_kernel_session_path():
    async def run():
        server = RuntimeServer.create(mock=True)
        result = await server.scheduler.run_app("inspection_agent", place="厨房", mock=True)
        assert result["result"]["success"] is True

        session = server.session_manager.get_session(result["session_id"])
        assert session is not None
        assert session.status == "completed"

        syscalls = server.session_manager.read_syscalls(result["session_id"], limit=100)
        final_skill_names = {record.get("skill_name") for record in syscalls if record.get("audit_id")}
        assert "robot.navigate_to" in final_skill_names
        assert "robot.inspect_area" in final_skill_names

        context = server.context_manager.recover(result["session_id"])
        assert context is not None
        assert context.app_id == "inspection_agent"

    asyncio.run(run())
