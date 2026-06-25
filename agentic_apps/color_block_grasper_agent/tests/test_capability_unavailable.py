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


class ScriptedColorBlockBackend:
    def __init__(self, *, verification_result: dict[str, object] | None = None):
        self.calls: list[dict[str, object]] = []
        self.verification_result = verification_result or _verify_success()

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
            return {"success": True, "answer": "CONFIRM", "error_code": "", "reason": "", "audit_id": "audit_human"}
        if skill_name == "robot.get_state":
            return {"success": True, "state": {"robot_id": "real_robot", "estop_pressed": False}, "error_code": "", "reason": ""}
        if skill_name == "arm.get_state":
            return {
                "success": True,
                "state": {
                    "readiness": "ready",
                    "gripper_ready": True,
                    "stop_available": True,
                    "holding_object": False,
                },
                "error_code": "",
                "reason": "",
            }
        if skill_name == "arm.move_named":
            return {"success": True, "result": {"action_name": args["name"], "status": "finished"}, "error_code": "", "reason": ""}
        if skill_name == "perception.center_color_block":
            return {
                "success": True,
                "alignment": {"centered": True, "target_color": args["color"], "evidence_image_path": "/tmp/center.png"},
                "evidence": {"kind": "color_block_alignment", "centered": True, "debug_image_path": "/tmp/center.png"},
                "error_code": "",
                "reason": "",
            }
        if skill_name == "perception.detect_color_block":
            return {"success": True, "detection": _detection(), "evidence": {"kind": "color_block_detection"}, "error_code": "", "reason": ""}
        if skill_name == "perception.capture_photo":
            label = str(args.get("label") or "photo")
            return {
                "success": True,
                "image_path": f"/tmp/{label}.png",
                "metadata_path": f"/tmp/{label}.json",
                "evidence": {"image_path": f"/tmp/{label}.png", "metadata_path": f"/tmp/{label}.json", "label": label},
                "error_code": "",
                "reason": "",
            }
        if skill_name == "manipulation.pick_color_block":
            return {
                "success": True,
                "result": {
                    "bridge_action": "/agentic/manipulation/pick_color_block",
                    "color": "red",
                    "held": True,
                    "duration_s": 1.0,
                },
                "error_code": "",
                "reason": "",
            }
        if skill_name == "perception.verify_held_color_block":
            return dict(self.verification_result)
        if skill_name == "manipulation.place_color_block":
            return {
                "success": True,
                "result": {
                    "bridge_action": "/agentic/manipulation/place_color_block",
                    "place_target": args["place_target"],
                    "held": True,
                    "released": False,
                },
                "error_code": "",
                "reason": "",
            }
        if skill_name == "report.say":
            return {"success": True, "message": args["message"], "error_code": "", "reason": ""}
        return {"success": False, "error_code": "SKILL_BACKEND_UNAVAILABLE", "reason": f"no script for {skill_name}"}

    def status(self):
        return {"success": True, "state": "ready", "active_calls": []}


class RobotCapabilityTestAdapter:
    def __init__(self, skill_backend):
        self.skill_backend = skill_backend

    def execute_capability(self, syscall):
        query = getattr(syscall, "query", None)
        skill_name = str(getattr(query, "skill_name", "") or syscall.params.get("skill_name") or syscall.operation_type)
        args = dict(syscall.params.get("args") or syscall.params.get("parameters") or syscall.params)
        return self.skill_backend.call(
            skill_name,
            args,
            app_id=str(getattr(query, "app_id", "") or syscall.agent_name),
            session_id=str(getattr(query, "session_id", "") or "sess_color"),
            permissions=tuple(getattr(query, "metadata", {}).get("permissions") or args.get("permissions") or ()),
            call_id=str(getattr(query, "call_id", "") or args.get("call_id") or ""),
        )


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


def test_color_block_normalizes_detection_evidence_for_pick_payload():
    module = _load_module()
    step = {
        "data": {
            "result": {
                "data": {
                    "detection": {},
                    "evidence": {
                        "kind": "color_block_detection",
                        "detection_id": "det_test",
                        "color": "red",
                        "center_px": [320.0, 240.0],
                        "confidence": 0.91,
                        "camera_position_m": [0.1, 0.2, 0.3],
                    },
                }
            }
        }
    }

    normalized = module._normalized_detection_data(step)
    validation = module._validate_detection_data({"color": "red"}, normalized)

    assert normalized["color"] == "red"
    assert normalized["camera_position_m"] == [0.1, 0.2, 0.3]
    assert validation["success"] is True


def test_pick_backend_held_true_but_post_pick_verification_false_fails(tmp_path):
    backend = ScriptedColorBlockBackend(verification_result=_verify_failed())
    result, _llm_chat = asyncio.run(
        _run_bare_kernel(tmp_path, llm_chat=RecordingLLMChat(_plan()), message="夹起红色方块", skill_backend=backend)
    )

    assert result["success"] is False
    assert result["error_code"] == "COLOR_BLOCK_PICK_VERIFICATION_FAILED"
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["pick_color_block"]["success"] is True
    assert by_name["post_pick_verify"]["success"] is False
    assert "place_color_block" not in by_name


def test_red_block_disappeared_without_held_roi_candidate_cannot_succeed(tmp_path):
    backend = ScriptedColorBlockBackend(verification_result=_verify_bad_success_without_candidate())
    result, _llm_chat = asyncio.run(
        _run_bare_kernel(tmp_path, llm_chat=RecordingLLMChat(_plan()), message="夹起红色方块", skill_backend=backend)
    )

    assert result["success"] is False
    assert result["error_code"] == "COLOR_BLOCK_PICK_VERIFICATION_FAILED"
    assert "held color candidate" in result["missing"]
    assert result.get("verified_held") is not True


def test_post_pick_verification_unavailable_is_stable_failure(tmp_path):
    backend = ScriptedColorBlockBackend(
        verification_result={
            "success": False,
            "verified_held": False,
            "error_code": "SKILL_NOT_FOUND",
            "reason": "verify_held_color_block backend unavailable",
        }
    )
    result, _llm_chat = asyncio.run(
        _run_bare_kernel(tmp_path, llm_chat=RecordingLLMChat(_plan()), message="夹起红色方块", skill_backend=backend)
    )

    assert result["success"] is False
    assert result["error_code"] == "COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE"
    assert "perception.verify_held_color_block" in result["missing"]


def test_verified_held_true_is_required_for_success(tmp_path):
    backend = ScriptedColorBlockBackend(verification_result=_verify_success())
    result, _llm_chat = asyncio.run(
        _run_bare_kernel(tmp_path, llm_chat=RecordingLLMChat(_plan()), message="夹起红色方块", skill_backend=backend)
    )

    assert result["success"] is True
    assert result["planner_mode"] == "llm"
    assert result["verified_held"] is True
    assert result["post_pick_evidence"]["image_path"].endswith("_post_pick.png")
    assert result["post_pick_gripper_state"]["state"]["gripper_ready"] is True
    assert result["post_pick_verification"]["verified_held"] is True
    by_name = {step["name"]: step for step in result["steps"]}
    assert by_name["post_pick_gripper_state"]["success"] is True
    assert by_name["capture_post_pick_evidence"]["success"] is True
    assert by_name["post_pick_verify"]["success"] is True
    assert by_name["place_color_block"]["success"] is True


async def _run_bare_kernel(tmp_path, *, llm_chat, message: str, skill_backend=None):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))
    if llm_chat is not None:
        service.runtime_server = SimpleNamespace(llm_chat=llm_chat)
    service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()
    service.skill.backend = skill_backend or RecordingSkillBackend()
    if skill_backend is not None:
        adapter = RobotCapabilityTestAdapter(skill_backend)
        service.robot_sensor.skill_adapter = adapter
        service.robot_motion.skill_adapter = adapter
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
                "perception.center.color_block",
                "perception.capture",
                "perception.verify.color_block_held",
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
        "steps": ["detect_color_block", "capture_evidence", "pick_color_block", "post_pick_verify", "place_color_block"],
        "risk_class": "manipulation_real_hardware",
        "user_summary": "Move the requested color block to the left tray.",
        "target": "workspace",
        "evidence_label": "red_block_left_tray",
        "timeout_s": 180,
    }


def _detection():
    return {
        "detection_id": "det_test",
        "color": "red",
        "target": "workspace",
        "confidence": 0.91,
        "center_px": [320.0, 240.0],
        "camera_position_m": [0.1, 0.2, 0.3],
        "evidence_image_path": "/tmp/pre.png",
        "evidence_metadata_path": "/tmp/pre.json",
    }


def _verify_success():
    return {
        "success": True,
        "verified_held": True,
        "verification": {
            "verification_id": "held_test",
            "verified_held": True,
            "target_color": "red",
            "method": "vision_color_in_gripper_held_roi",
            "candidate": {"center_px": [240.0, 330.0], "radius_px": 48.0, "area_px": 500.0},
            "radius_ratio_vs_pre_pick": 1.3,
            "min_radius_ratio_vs_pre_pick": 1.15,
            "size_confirms_lift": True,
            "position_confirms_gripper_roi": True,
            "overlaps_pre_pick_detection": False,
            "evidence_image_path": "/tmp/held.png",
            "evidence_metadata_path": "/tmp/held.json",
        },
        "evidence": {
            "verified_held": True,
            "size_confirms_lift": True,
            "position_confirms_gripper_roi": True,
            "overlaps_pre_pick_detection": False,
            "radius_ratio_vs_pre_pick": 1.3,
            "min_radius_ratio_vs_pre_pick": 1.15,
            "debug_image_path": "/tmp/held.png",
            "metadata_path": "/tmp/held.json",
        },
        "error_code": "",
        "reason": "",
    }


def _verify_failed():
    return {
        "success": False,
        "verified_held": False,
        "verification": {
            "verified_held": False,
            "target_color": "red",
            "candidate": {},
            "evidence_image_path": "/tmp/post_pick.png",
            "evidence_metadata_path": "/tmp/post_pick.json",
        },
        "evidence": {"verified_held": False, "debug_image_path": "/tmp/post_pick.png", "metadata_path": "/tmp/post_pick.json"},
        "error_code": "COLOR_BLOCK_PICK_VERIFICATION_FAILED",
        "reason": "red block was not detected in held ROI",
    }


def _verify_bad_success_without_candidate():
    return {
        "success": True,
        "verified_held": False,
        "verification": {
            "verified_held": False,
            "target_color": "red",
            "candidate": {},
            "evidence_image_path": "/tmp/post_pick.png",
            "evidence_metadata_path": "/tmp/post_pick.json",
        },
        "evidence": {"verified_held": False, "debug_image_path": "/tmp/post_pick.png", "metadata_path": "/tmp/post_pick.json"},
        "error_code": "",
        "reason": "",
    }


def _load_run():
    return _load_module().run


def _load_module():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("color_block_grasper_agent_main", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
