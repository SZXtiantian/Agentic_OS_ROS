import asyncio

from agentic_runtime.app_invoker import AppInvoker
from agentic_runtime.dispatcher.app_index import AppIndex, AppIndexEntry
from runtime_test_helpers import create_test_runtime_server


def test_app_invoker_loads_aios_robot_photographer_and_reports_missing_bridge(tmp_path, monkeypatch, app_root):
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path / "raw"))
    monkeypatch.setenv("AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT", str(tmp_path / "app_storage"))

    async def run():
        server = create_test_runtime_server()
        invoker = AppInvoker(server, AppIndex.load(app_root))
        result = await invoker.run_app(
            "robot_photographer_agent",
            {"text": "拍一张照片"},
            parent_session_id="sess_parent",
            route_plan_id="plan_route",
        )
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert result["session_id"]
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/safety/check"

    asyncio.run(run())


def test_app_invoker_rejects_simulated_task_input_before_loading_runtime(app_root):
    async def run():
        server = create_test_runtime_server()
        invoker = AppInvoker(server, AppIndex.load(app_root))
        result = await invoker.run_app(
            "robot_photographer_agent",
            {"text": "拍一张照片", "mock": True},
            parent_session_id="sess_parent",
            route_plan_id="plan_route",
        )
        assert result["status"] == "failed"
        assert result["session_id"] == ""
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "TASK_INPUT_FIELD_UNSUPPORTED"
        assert server.test_bridge_calls == []

    asyncio.run(run())


def test_app_invoker_rejects_aios_result_missing_success(tmp_path):
    app_dir = tmp_path / "invalid_aios_agent"
    app_dir.mkdir()
    (app_dir / "entry.py").write_text(
        "\n".join(
            [
                "class InvalidAgent:",
                "    def __init__(self, **kwargs):",
                "        self.kwargs = kwargs",
                "    async def arun(self, task_input):",
                "        return {'message': 'missing result contract'}",
            ]
        ),
        encoding="utf-8",
    )
    entry = AppIndexEntry(
        app_id="invalid_aios_agent",
        root=str(app_dir),
        dispatch_enabled=True,
        runtime_type="aios_agent_package",
        aios_entrypoint="entry:InvalidAgent",
    )
    invoker = AppInvoker(create_test_runtime_server(), AppIndex([entry]))

    async def run():
        result = await invoker.run_app(
            "invalid_aios_agent",
            {"text": "run"},
            parent_session_id="sess_parent",
            route_plan_id="plan",
        )
        assert result["success"] is False
        assert result["error_code"] == "APP_RESULT_INVALID"
        assert result["metadata"]["keys"] == ["message"]

    asyncio.run(run())


def test_app_invoker_aios_constructor_does_not_receive_mock_default(tmp_path):
    app_dir = tmp_path / "runtime_only_agent"
    app_dir.mkdir()
    (app_dir / "entry.py").write_text(
        "\n".join(
            [
                "class RuntimeOnlyAgent:",
                "    def __init__(self, runtime):",
                "        self.runtime = runtime",
                "    async def arun(self, task_input):",
                "        return {'success': True, 'task_input': task_input}",
            ]
        ),
        encoding="utf-8",
    )
    entry = AppIndexEntry(
        app_id="runtime_only_agent",
        root=str(app_dir),
        dispatch_enabled=True,
        runtime_type="aios_agent_package",
        aios_entrypoint="entry:RuntimeOnlyAgent",
    )
    invoker = AppInvoker(create_test_runtime_server(), AppIndex([entry]))

    async def run():
        result = await invoker.run_app(
            "runtime_only_agent",
            {"text": "run"},
            parent_session_id="sess_parent",
            route_plan_id="plan",
        )
        assert result["success"] is True
        assert result["task_input"]["text"] == "run"
        assert "mock" not in result["task_input"]

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
        assert "mock" not in result["result"]["kwargs"]

    asyncio.run(run())


def test_app_invoker_rejects_legacy_wrapper_result_missing_success():
    async def invalid_run_app(app_id, **kwargs):
        return {"session_id": "sess_legacy", "app_id": app_id, "status": "completed", "result": {"message": "missing"}}

    class Runtime:
        class Scheduler:
            run_app = staticmethod(invalid_run_app)

        scheduler = Scheduler()

    entry = AppIndexEntry(app_id="legacy_agent", root="/tmp/legacy", dispatch_enabled=True, entrypoint="main:run")
    invoker = AppInvoker(Runtime(), AppIndex([entry]))

    async def run():
        result = await invoker.run_app("legacy_agent", {}, parent_session_id="sess_parent", route_plan_id="plan")
        assert result["success"] is False
        assert result["status"] == "failed"
        assert result["result"]["success"] is False
        assert result["result"]["error_code"] == "APP_RESULT_INVALID"

    asyncio.run(run())
