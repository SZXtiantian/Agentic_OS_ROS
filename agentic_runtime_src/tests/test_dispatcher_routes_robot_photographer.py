import asyncio
from pathlib import Path

from agentic_runtime.dispatcher import DispatcherAgent
from agentic_runtime.dispatcher.app_index import AppIndex
from agentic_runtime.dispatcher.errors import DispatchError
from agentic_runtime.dispatcher.planner import DispatcherPlanner
from agentic_runtime.dispatcher.validation import DispatcherValidator
from agentic_runtime.nl_gateway import GatewayFlags
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server


def _plan(app_root, text: str, flags=None):
    planner = DispatcherPlanner()
    return planner.plan(
        text,
        AppIndex.load(app_root),
        flags or GatewayFlags(mock=True),
        task_id="task_test",
        route_plan_id="plan_route_test",
    )


def test_photo_routes_to_robot_photographer(app_root):
    plan = _plan(app_root, "拍一张工作区照片")
    assert plan["selected_app_id"] == "robot_photographer_agent"
    assert plan["intent"] == "capture_photo"
    assert plan["risk_class"] == "read_only"


def test_recent_photos_routes_to_robot_photographer(app_root):
    plan = _plan(app_root, "查看最近照片")
    assert plan["selected_app_id"] == "robot_photographer_agent"
    assert plan["intent"] == "recent_photos"


def test_recent_tasks_is_builtin(app_root):
    plan = _plan(app_root, "最近任务")
    assert plan["selected_app_id"] == "builtin.tasks"
    assert plan["intent"] == "tasks"


def test_last_task_is_builtin(app_root):
    plan = _plan(app_root, "上一个任务的结果")
    assert plan["selected_app_id"] == "builtin.last_task"
    assert plan["intent"] == "last_task"


def test_dispatcher_writes_task_log_and_runs_read_only_photo(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_TASK_LOG_ROOT", str(tmp_path / "tasks"))
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path / "raw_photos"))
    monkeypatch.setenv("AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT", str(tmp_path / "app_storage"))

    async def run():
        server = create_test_runtime_server()
        result = await DispatcherAgent(server).arun("拍一张照片", GatewayFlags(mock=True, json=True))
        assert result["success"] is True
        assert result["selected_app_id"] == "robot_photographer_agent"
        assert result["selected_agents"][0]["agent_id"] == "robot_photographer_agent"
        assert result["result_summary"]["app_output_paths"]
        assert result["result_summary"]["raw_evidence_paths"]
        assert Path(result["task_log_path"]).exists()
        recent = server.task_log_manager.list_recent(limit=5)
        assert recent[0].task_id == result["task_id"]
        assert recent[0].status == "completed"

    asyncio.run(run())


def test_robot_photographer_dispatch_manifest_registered(app_root):
    entry = AppIndex.load(app_root).get("robot_photographer_agent")
    assert entry is not None
    assert entry.dispatch_enabled is True
    assert "capture_photo" in entry.intents
    assert "workspace" in entry.allowed_targets


def test_show_plan_dry_run_does_not_execute_app(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_TASK_LOG_ROOT", str(tmp_path / "tasks"))

    async def run():
        server = create_test_runtime_server()
        result = await DispatcherAgent(server).arun(
            "拍一组多角度照片",
            GatewayFlags(mock=True, show_plan=True, dry_run=True),
        )
        assert result["success"] is True
        assert result["status"] == "dry_run"
        assert result["app_result"] == {}
        assert result["route_plan"]["selected_app_id"] == "robot_photographer_agent"

    asyncio.run(run())


def test_route_validation_accepts_enabled_app(app_root):
    plan = _plan(app_root, "拍一张照片")
    validated = DispatcherValidator().validate(plan, AppIndex.load(app_root), GatewayFlags(mock=True))
    assert validated["validated"] is True


def test_require_llm_rejects_dispatcher_rule_fallback(app_root):
    class BadLLMChat:
        def chat_json(self, *, system_prompt, user_prompt):
            raise RuntimeError("network down")

    planner = DispatcherPlanner(llm_chat=BadLLMChat())
    flags = GatewayFlags(mock=True, require_llm=True)

    try:
        planner.plan(
            "拍一张照片",
            AppIndex.load(app_root),
            flags,
            task_id="task_test",
            route_plan_id="plan_route_test",
        )
    except DispatchError as exc:
        assert exc.code == "DISPATCH_LLM_REQUIRED_FAILED"
    else:
        raise AssertionError("required LLM planning must not fall back to rule_based")
