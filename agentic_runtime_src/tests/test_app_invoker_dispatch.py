import asyncio

from agentic_runtime.app_invoker import AppInvoker
from agentic_runtime.dispatcher.app_index import AppIndex, AppIndexEntry
from agentic_runtime.server import RuntimeServer


def test_app_invoker_loads_aios_robot_photographer(tmp_path, monkeypatch, app_root):
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path / "raw"))
    monkeypatch.setenv("AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT", str(tmp_path / "app_storage"))

    async def run():
        server = RuntimeServer.create(mock=True)
        invoker = AppInvoker(server, AppIndex.load(app_root))
        result = await invoker.run_app(
            "robot_photographer_agent",
            {"text": "拍一张照片", "mock": True},
            parent_session_id="sess_parent",
            route_plan_id="plan_route",
        )
        assert result["result"]["success"] is True
        assert result["session_id"]

    asyncio.run(run())


def test_app_invoker_legacy_app_uses_scheduler(monkeypatch):
    async def fake_run_app(app_id, **kwargs):
        return {"session_id": "sess_legacy", "app_id": app_id, "status": "completed", "result": {"success": True, "kwargs": kwargs}}

    class Runtime:
        class Scheduler:
            run_app = staticmethod(fake_run_app)

        scheduler = Scheduler()

    entry = AppIndexEntry(app_id="legacy_agent", root="/tmp/legacy", dispatch_enabled=True, entrypoint="main:run")
    invoker = AppInvoker(Runtime(), AppIndex([entry]))

    async def run():
        result = await invoker.run_app("legacy_agent", {"place": "workspace"}, parent_session_id="sess_parent", route_plan_id="plan")
        assert result["result"]["success"] is True
        assert result["result"]["kwargs"]["route_plan_id"] == "plan"

    asyncio.run(run())
