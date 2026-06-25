import asyncio
import json
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
        flags or GatewayFlags(),
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


def test_dispatcher_writes_failed_task_log_when_photo_bridge_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_TASK_LOG_ROOT", str(tmp_path / "tasks"))
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path / "raw_photos"))
    monkeypatch.setenv("AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT", str(tmp_path / "app_storage"))

    async def run():
        server = create_test_runtime_server()
        result = await DispatcherAgent(server).arun("拍一张照片", GatewayFlags(json=True))
        assert result["success"] is False
        assert result["status"] == "failed"
        assert result["error_code"] == "ROS_BRIDGE_UNAVAILABLE"
        assert result["selected_app_id"] == "robot_photographer_agent"
        assert result["selected_agents"][0]["agent_id"] == "robot_photographer_agent"
        assert result["result_summary"]["app_output_paths"] == []
        assert result["result_summary"]["raw_evidence_paths"] == []
        assert Path(result["task_log_path"]).exists()
        recent = server.task_log_manager.list_recent(limit=5)
        assert recent[0].task_id == result["task_id"]
        assert recent[0].status == "failed"
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/safety/check"

    asyncio.run(run())


def test_dispatcher_rejects_non_boolean_app_success(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_TASK_LOG_ROOT", str(tmp_path / "tasks"))

    class MalformedExecutor:
        async def execute(self, plan, *, parent_session_id):
            return {
                "session_id": "sess_malformed",
                "result": {"success": "false", "reason": "string success"},
            }

    async def run():
        server = create_test_runtime_server()
        result = await DispatcherAgent(server, executor=MalformedExecutor()).arun(
            "拍一张照片",
            GatewayFlags(json=True),
        )
        assert result["success"] is False
        assert result["status"] == "failed"
        assert result["error_code"] == "DISPATCH_APP_RESULT_INVALID"
        assert "result.success field must be boolean" in result["message"]
        recent = server.task_log_manager.list_recent(limit=5)
        assert recent[0].status == "failed"
        assert recent[0].error_code == "DISPATCH_APP_RESULT_INVALID"

    asyncio.run(run())


def test_dispatcher_requires_nested_app_result_success(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_TASK_LOG_ROOT", str(tmp_path / "tasks"))

    class MissingNestedSuccessExecutor:
        async def execute(self, plan, *, parent_session_id):
            return {
                "success": True,
                "session_id": "sess_missing",
                "result": {"summary": "missing nested success"},
            }

    async def run():
        server = create_test_runtime_server()
        result = await DispatcherAgent(server, executor=MissingNestedSuccessExecutor()).arun(
            "拍一张照片",
            GatewayFlags(json=True),
        )
        assert result["success"] is False
        assert result["error_code"] == "DISPATCH_APP_RESULT_INVALID"
        assert result["message"] == "result.success field is required"

    asyncio.run(run())


def test_robot_photographer_dispatch_manifest_registered(app_root):
    entry = AppIndex.load(app_root).get("robot_photographer_agent")
    assert entry is not None
    assert entry.dispatch_enabled is True
    assert "capture_photo" in entry.intents
    assert "workspace" in entry.allowed_targets


def test_color_block_dispatch_manifest_registered(app_root):
    entry = AppIndex.load(app_root).get("color_block_grasper_agent")
    assert entry is not None
    assert entry.dispatch_enabled is True
    assert "color_block_grasp" in entry.intents
    assert "named_motion" in entry.risk_classes
    assert "workspace" in entry.allowed_targets


def test_dispatcher_llm_prompt_includes_color_block_app(app_root):
    class RoutingLLMChat:
        def chat_json(self, *, system_prompt, user_prompt):
            del system_prompt
            prompt = json.loads(user_prompt)
            assert "color_block_grasper_agent" in prompt["allowed_selected_app_ids"]
            assert "color_block_grasp" in prompt["allowed_intents"]
            return {
                "schema_version": "1.0",
                "task_id": prompt["required_task_id"],
                "route_plan_id": prompt["required_route_plan_id"],
                "created_at": prompt["created_at"],
                "user_text": prompt["user_text"],
                "planner_mode": "llm",
                "intent": "color_block_grasp",
                "selected_app_id": "color_block_grasper_agent",
                "route_reason": "color block app owns real grasp tasks",
                "risk_class": "named_motion",
                "requires_robot_motion": False,
                "needs_confirmation": False,
                "target": "workspace",
                "app_task_input": {"text": prompt["user_text"]},
                "preflight_checks": [],
                "fallback": {"used": False, "reason": ""},
                "user_summary": "夹起红色方块",
            }

    app_index = AppIndex.load(app_root)
    flags = GatewayFlags(require_llm=True, allow_arm_motion=True, assume_yes=True)
    plan = DispatcherPlanner(llm_chat=RoutingLLMChat()).plan(
        "夹起红色方块",
        app_index,
        flags,
        task_id="task_test",
        route_plan_id="plan_route_test",
    )
    assert plan["selected_app_id"] == "color_block_grasper_agent"
    assert plan["planner_mode"] == "llm"
    assert plan["requires_robot_motion"] is True
    assert plan["needs_confirmation"] is True
    validated = DispatcherValidator().validate(plan, app_index, flags)
    assert validated["intent"] == "color_block_grasp"


def test_forced_color_block_app_overrides_unsupported_llm_route(app_root):
    class UnsupportedLLMChat:
        def chat_json(self, *, system_prompt, user_prompt):
            del system_prompt
            prompt = json.loads(user_prompt)
            return {
                "schema_version": "1.0",
                "task_id": prompt["required_task_id"],
                "route_plan_id": prompt["required_route_plan_id"],
                "created_at": prompt["created_at"],
                "user_text": prompt["user_text"],
                "planner_mode": "llm",
                "intent": "unsupported",
                "selected_app_id": "unsupported",
                "route_reason": "model declined route",
                "risk_class": "unsupported",
                "requires_robot_motion": False,
                "needs_confirmation": False,
                "target": "workspace",
                "app_task_input": {"text": prompt["user_text"]},
                "preflight_checks": [],
                "fallback": {"used": False, "reason": ""},
                "user_summary": "unsupported",
            }

    app_index = AppIndex.load(app_root)
    flags = GatewayFlags(
        require_llm=True,
        allow_arm_motion=True,
        assume_yes=True,
        forced_app_id="color_block_grasper_agent",
    )
    plan = DispatcherPlanner(llm_chat=UnsupportedLLMChat()).plan(
        "夹起红色方块",
        app_index,
        flags,
        task_id="task_test",
        route_plan_id="plan_route_test",
    )
    assert plan["selected_app_id"] == "color_block_grasper_agent"
    assert plan["intent"] == "color_block_grasp"
    assert plan["risk_class"] == "named_motion"
    assert plan["requires_robot_motion"] is True
    assert plan["needs_confirmation"] is True
    DispatcherValidator().validate(plan, app_index, flags)


def test_show_plan_dry_run_does_not_execute_app(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_TASK_LOG_ROOT", str(tmp_path / "tasks"))

    async def run():
        server = create_test_runtime_server()
        result = await DispatcherAgent(server).arun(
            "拍一组多角度照片",
            GatewayFlags(show_plan=True, dry_run=True),
        )
        assert result["success"] is True
        assert result["status"] == "dry_run"
        assert result["app_result"] == {}
        assert result["route_plan"]["selected_app_id"] == "robot_photographer_agent"

    asyncio.run(run())


def test_route_validation_accepts_enabled_app(app_root):
    plan = _plan(app_root, "拍一张照片")
    validated = DispatcherValidator().validate(plan, AppIndex.load(app_root), GatewayFlags())
    assert validated["validated"] is True


def test_require_llm_rejects_dispatcher_rule_fallback(app_root):
    class BadLLMChat:
        def chat_json(self, *, system_prompt, user_prompt):
            raise RuntimeError("network down")

    planner = DispatcherPlanner(llm_chat=BadLLMChat())
    flags = GatewayFlags(require_llm=True)

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
