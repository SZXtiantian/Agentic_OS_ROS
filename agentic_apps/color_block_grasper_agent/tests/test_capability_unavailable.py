from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


RUNTIME_SRC = Path(__file__).resolve().parents[3] / "agentic_runtime_src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from agentic_os.kernel.access import AlwaysAllowTestInterventionProvider
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest


class RecordingLLMChat:
    def __init__(self, plan):
        self.plan = dict(plan)
        self.calls: list[dict[str, str]] = []

    def chat_json(self, *, system_prompt: str, user_prompt: str):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return dict(self.plan)


class RecordingSkillBackend:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def call(self, skill_name, args, *, app_id, session_id, permissions=(), call_id=""):
        self.calls.append(
            {
                "skill_name": skill_name,
                "args": dict(args),
                "app_id": app_id,
                "session_id": session_id,
                "permissions": tuple(permissions),
                "call_id": call_id,
            }
        )
        if skill_name == "human.ask":
            return {
                "success": True,
                "skill_name": skill_name,
                "result": {"success": True, "data": {"answer": "CONFIRM"}},
                "error_code": "",
                "reason": "",
                "audit_id": "audit_human_confirmed",
            }
        return {
            "success": False,
            "skill_name": skill_name,
            "result": {"success": False, "error_code": "SKILL_BACKEND_UNAVAILABLE", "data": {}},
            "error_code": "SKILL_BACKEND_UNAVAILABLE",
            "reason": f"{skill_name} backend unavailable in test runtime",
            "audit_id": "",
        }

    def status(self):
        return {"success": True, "state": "ready", "active_calls": []}


class ConfirmingHumanBackend:
    def __init__(self):
        self.calls = []

    def address_request(self, syscall):
        self.calls.append(syscall)
        return {"success": True, "answered": True, "answer": "CONFIRM", "audit_id": "audit_human_confirmed"}

    def status(self):
        return {"success": True, "state": "ready", "active_calls": []}


def test_color_block_requires_runtime_llm_facade(tmp_path):
    result, llm_chat = asyncio.run(
        _run_bare_kernel(tmp_path, llm_chat=None, message="把红色颜色块夹到左边托盘")
    )

    assert llm_chat is None
    assert result["success"] is False
    assert result["error_code"] == "LLMCHAT_UNAVAILABLE"
    assert "RuntimeServer.llm_chat" in result["missing"]
    assert result["next_action"]
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["llm_plan"]["success"] is False
    assert "check_robot" not in by_name


def test_color_block_invalid_llm_plan_is_rejected_before_robot_skills(tmp_path):
    llm_chat = RecordingLLMChat(_plan(target_color="purple"))
    result, llm_chat = asyncio.run(
        _run_bare_kernel(tmp_path, llm_chat=llm_chat, message="把紫色颜色块夹到左边托盘")
    )

    assert result["success"] is False
    assert llm_chat.calls
    assert result["error_code"] == "COLOR_BLOCK_LLM_PLAN_INVALID"
    assert result["planner_mode"] == "llm"
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["llm_plan"]["success"] is True
    assert by_name["validate_plan"]["success"] is False
    assert "check_robot" not in by_name


def test_color_block_llm_plan_reaches_real_backend_unavailable(tmp_path):
    llm_chat = RecordingLLMChat(_plan())
    result, llm_chat = asyncio.run(
        _run_bare_kernel(tmp_path, llm_chat=llm_chat, message="把红色颜色块夹到左边托盘")
    )

    assert llm_chat.calls
    assert "把红色颜色块夹到左边托盘" in llm_chat.calls[0]["user_prompt"]
    assert result["success"] is False
    assert result["error_code"] == "UNVERIFIED_REAL_DEPENDENCY"
    assert result["planner_mode"] == "llm"
    assert result["plan"]["target_color"] == "red"
    assert "robot.get_state" in result["missing"]
    assert result["report_error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["llm_plan"]["success"] is True
    assert by_name["validate_plan"]["success"] is True
    assert by_name["validate_policy"]["success"] is True
    assert by_name["human_confirmation"]["success"] is True
    assert by_name["check_robot"]["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    assert by_name["write_result"]["success"] is True
    assert result["syscall_ids"]


async def _run_bare_kernel(tmp_path, *, llm_chat, message: str):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))
    if llm_chat is not None:
        service.runtime_server = SimpleNamespace(llm_chat=llm_chat)
    service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()
    service.skill.backend = RecordingSkillBackend()
    service.human.human_adapter = ConfirmingHumanBackend()

    class Executor:
        kernel_service = service

        async def execute(self, *args, **execute_kwargs):
            raise AssertionError("color_block_grasper_agent must use kernel skill syscalls")

    service.start()
    try:
        app = AppManifest(
            "color_block_grasper_agent",
            "0.1.0",
            "",
            "main:run",
            [
                "llm.external.call",
                "robot.state.read",
                "arm.state.read",
                "human.ask",
                "perception.detect.color_block",
                "perception.capture",
                "manipulation.pick.color_block",
                "manipulation.place.color_block",
                "memory.write",
                "storage.write",
                "storage.read",
                "report.say",
            ],
            ["agenticos.runtime.llm_chat", "llm.chat"],
        )
        ctx = AgentContext(Executor(), app, "sess_color")
        return await _load_run()(ctx, message=message), llm_chat
    finally:
        service.stop()


def _plan(*, target_color: str = "red"):
    return {
        "schema_version": "1.0",
        "planner_mode": "llm",
        "target_color": target_color,
        "place_target": "left_tray",
        "requires_manipulation": True,
        "needs_confirmation": True,
        "steps": ["detect_color_block", "capture_evidence", "pick_color_block", "place_color_block"],
        "risk_class": "manipulation_real_hardware",
        "user_summary": "Move the requested color block to the left tray.",
        "target": "workspace",
        "evidence_label": "red_block_left_tray",
        "timeout_s": 180,
    }


def _load_run():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("color_block_grasper_agent_main", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run
