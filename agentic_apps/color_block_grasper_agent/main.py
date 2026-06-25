from __future__ import annotations

import asyncio
from typing import Any

from agentic_runtime.sdk import AgentContext


APP_ID = "color_block_grasper_agent"
PLAN_SCHEMA_VERSION = "1.0"
HOLD_STABILITY_DELAY_S = 2.0
ALLOWED_COLORS = {"red", "green", "blue", "yellow"}
CONFIRM_ANSWER = "CONFIRM"
PLAN_STEPS = [
    "detect_color_block",
    "capture_evidence",
    "pick_color_block",
    "post_pick_verify",
    "place_color_block",
]
RISK_CLASSES = {"controlled_manipulation", "manipulation_real_hardware"}


async def run(ctx: AgentContext, **kwargs: Any) -> dict[str, Any]:
    task_text = str(kwargs.get("task_text") or kwargs.get("message") or kwargs.get("text") or "").strip()
    steps: list[dict[str, Any]] = []

    if not task_text:
        return await _finish_failure(
            ctx,
            {"task_text": "", "planner_mode": "", "plan": {}},
            steps,
            {
                "success": False,
                "error_code": "COLOR_BLOCK_LLM_PLAN_REQUIRED",
                "reason": "natural language task_text or message is required for system LLM planning",
                "missing": ["task_text"],
                "next_action": "Provide a natural language color-block manipulation request and rerun.",
            },
        )

    plan_result = await _plan_with_system_llm(ctx, task_text)
    steps.append(_llm_step("llm_plan", plan_result))
    if not plan_result["success"]:
        return await _finish_failure(
            ctx,
            {"task_text": task_text, "planner_mode": "", "plan": {}},
            steps,
            {
                "success": False,
                "error_code": str(plan_result["error_code"] or "COLOR_BLOCK_LLM_PLAN_REQUIRED"),
                "reason": str(plan_result["reason"] or "system LLM planning is required"),
                "missing": ["RuntimeServer.llm_chat"],
                "next_action": "Configure the Agentic OS Runtime LLM provider and rerun with LLM required.",
            },
        )

    plan = plan_result["plan"]
    validation = _validate_plan(plan)
    steps.append(_plan_validation_step(validation))
    if not validation["success"]:
        return await _finish_failure(ctx, {"task_text": task_text, "planner_mode": "llm", "plan": plan}, steps, validation)

    task = _task_from_plan(task_text, plan, operator_confirmed=bool(kwargs.get("assume_yes")))
    policy = _validate_policy(ctx, task)
    steps.append(
        {
            "name": "validate_policy",
            "skill": "deterministic.policy",
            "success": bool(policy["success"]),
            "error_code": str(policy.get("error_code") or ""),
            "reason": str(policy.get("reason") or ""),
            "data": {"risk_class": task["risk_class"], "permissions_checked": policy.get("permissions_checked", [])},
            "syscall_id": "",
            "audit_id": "",
        }
    )
    if not policy["success"]:
        return await _finish_failure(ctx, task, steps, policy)

    await _record_start(ctx, task, steps)

    confirmation = await _confirm_manipulation(ctx, task, steps)
    if not confirmation["success"]:
        return await _finish_failure(ctx, task, steps, confirmation)

    readiness = await _check_readiness(ctx, task, steps)
    if not readiness["success"]:
        return await _finish_failure(ctx, task, steps, readiness)

    detection = await _detect_color_block(ctx, task, steps)
    if not detection["success"]:
        return await _finish_failure(ctx, task, steps, detection)

    evidence = await _capture_evidence(ctx, task, steps)
    if not evidence["success"]:
        return await _finish_failure(ctx, task, steps, evidence)

    pick = await _pick_color_block(ctx, task, detection, evidence, steps)
    if not pick["success"]:
        return await _finish_failure(ctx, task, steps, pick)

    post_pick_verification = await _post_pick_verify(ctx, task, detection, pick, steps)
    if not post_pick_verification["success"]:
        return await _finish_failure(ctx, task, steps, post_pick_verification)

    place = await _place_color_block(ctx, task, pick, steps)
    if not place["success"]:
        return await _finish_failure(ctx, task, steps, place)

    return await _finish_success(ctx, task, detection, evidence, pick, post_pick_verification, place, steps)


async def _plan_with_system_llm(ctx: AgentContext, task_text: str) -> dict[str, Any]:
    result = await ctx.llm.chat_json(
        system_prompt=_system_prompt(),
        user_prompt=f"User task: {task_text}",
        timeout_s=30,
    )
    if not result.success:
        return {
            "success": False,
            "plan": {},
            "error_code": result.error_code or "COLOR_BLOCK_LLM_PLAN_REQUIRED",
            "reason": result.reason or "system LLM planning is required",
            "metadata": dict(result.metadata),
        }
    return {"success": True, "plan": dict(result.plan), "error_code": "", "reason": "", "metadata": dict(result.metadata)}


def _system_prompt() -> str:
    return "\n".join(
        [
            "You plan a color-block manipulation task for an Agentic OS Agent App.",
            "Return one raw JSON object only.",
            "Required fields:",
            "- schema_version: '1.0'",
            "- planner_mode: 'llm'",
            "- target_color: one of red, green, blue, yellow",
            "- place_target: 'hold_position' when the user asks only to pick/hold/grasp; otherwise a concrete tray or workspace destination",
            "- requires_manipulation: true",
            "- needs_confirmation: true",
            "- steps: exactly ['detect_color_block','capture_evidence','pick_color_block','post_pick_verify','place_color_block']",
            "- risk_class: 'controlled_manipulation' or 'manipulation_real_hardware'",
            "- user_summary: one short sentence",
            "Optional fields: target, evidence_label, timeout_s.",
            "Do not include markdown fences.",
        ]
    )


def _validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "planner_mode",
        "target_color",
        "place_target",
        "requires_manipulation",
        "needs_confirmation",
        "steps",
        "risk_class",
        "user_summary",
    ]
    missing = [field for field in required if field not in plan]
    if missing:
        return _plan_failure(f"LLM plan missing required fields: {', '.join(missing)}")
    if plan["schema_version"] != PLAN_SCHEMA_VERSION or plan["planner_mode"] != "llm":
        return _plan_failure("LLM plan schema_version/planner_mode invalid")
    if plan["target_color"] not in ALLOWED_COLORS:
        return _plan_failure("LLM plan target_color is outside the allowed color set")
    if not isinstance(plan["place_target"], str) or not plan["place_target"].strip():
        return _plan_failure("LLM plan place_target must be a non-empty string")
    if plan["requires_manipulation"] is not True:
        return _plan_failure("LLM plan must declare requires_manipulation=true")
    if not isinstance(plan["needs_confirmation"], bool):
        return _plan_failure("LLM plan needs_confirmation must be boolean")
    if plan["steps"] != PLAN_STEPS:
        return _plan_failure("LLM plan steps must use the required deterministic execution sequence")
    if plan["risk_class"] not in RISK_CLASSES:
        return _plan_failure("LLM plan risk_class is not allowed")
    if not isinstance(plan["user_summary"], str) or not plan["user_summary"].strip():
        return _plan_failure("LLM plan user_summary must be a non-empty string")
    if "target" in plan and (not isinstance(plan["target"], str) or not plan["target"].strip()):
        return _plan_failure("LLM plan target must be a non-empty string when present")
    if "evidence_label" in plan and (not isinstance(plan["evidence_label"], str) or not plan["evidence_label"].strip()):
        return _plan_failure("LLM plan evidence_label must be a non-empty string when present")
    if "timeout_s" in plan and (not isinstance(plan["timeout_s"], int) or plan["timeout_s"] < 1 or plan["timeout_s"] > 600):
        return _plan_failure("LLM plan timeout_s must be an integer between 1 and 600 when present")
    return {"success": True, "error_code": "", "reason": "", "missing": [], "next_action": ""}


def _plan_failure(reason: str) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": "COLOR_BLOCK_LLM_PLAN_INVALID",
        "reason": reason,
        "missing": [],
        "next_action": "Fix the Runtime LLM JSON plan contract and rerun.",
    }


def _task_from_plan(task_text: str, plan: dict[str, Any], *, operator_confirmed: bool = False) -> dict[str, Any]:
    color = str(plan["target_color"])
    return {
        "task_text": task_text,
        "planner_mode": "llm",
        "plan": dict(plan),
        "color": color,
        "target_color": color,
        "place_target": str(plan["place_target"]),
        "requires_manipulation": True,
        "needs_confirmation": bool(plan["needs_confirmation"]),
        "require_confirmation": bool(plan["needs_confirmation"]),
        "evidence_label": str(plan.get("evidence_label") or f"{color}_block_grasp"),
        "timeout_s": int(plan.get("timeout_s") or 180),
        "target": str(plan.get("target") or "workspace"),
        "risk_class": str(plan["risk_class"]),
        "user_summary": str(plan["user_summary"]),
        "steps": list(plan["steps"]),
        "operator_confirmed": bool(operator_confirmed),
        "operator_confirmation_source": "cli_yes_flag" if operator_confirmed else "",
    }


def _validate_policy(ctx: AgentContext, task: dict[str, Any]) -> dict[str, Any]:
    required_permissions = [
        "perception.detect.color_block",
        "perception.center.color_block",
        "perception.capture",
        "perception.verify.color_block_held",
        "manipulation.pick.color_block",
        "manipulation.place.color_block",
        "human.ask",
    ]
    permissions = set(ctx.app_manifest.permissions)
    missing = [permission for permission in required_permissions if permission not in permissions]
    if missing:
        return {
            "success": False,
            "error_code": "COLOR_BLOCK_CAPABILITY_UNAVAILABLE",
            "reason": "app manifest does not grant required color-block capability permissions",
            "missing": missing,
            "next_action": "Grant the required Agentic OS permissions in app.yaml and rerun.",
            "permissions_checked": required_permissions,
        }
    if not bool(task["requires_manipulation"]):
        return {
            "success": False,
            "error_code": "COLOR_BLOCK_LLM_PLAN_INVALID",
            "reason": "LLM plan did not declare the manipulation requirement",
            "missing": [],
            "next_action": "Regenerate the LLM plan with requires_manipulation=true.",
            "permissions_checked": required_permissions,
        }
    if not bool(task["needs_confirmation"]):
        return {
            "success": False,
            "error_code": "COLOR_BLOCK_LLM_PLAN_INVALID",
            "reason": "real color-block manipulation requires explicit human confirmation",
            "missing": ["human confirmation requirement"],
            "next_action": "Regenerate the LLM plan with needs_confirmation=true.",
            "permissions_checked": required_permissions,
        }
    return {"success": True, "permissions_checked": required_permissions}


async def _record_start(ctx: AgentContext, task: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    context = await ctx.kernel.context.put("color_block_grasper.task", task, timeout_s=5)
    steps.append(_step("record_context", "kernel.context.put", context))
    mount = await ctx.kernel.storage.mount("color_block_grasper_agent", timeout_s=5)
    steps.append(_step("mount_storage", "kernel.storage.mount", mount))
    start_record = await ctx.kernel.storage.write(
        f"color_block_grasper_agent/{ctx.session_id}_start.json",
        task,
        timeout_s=5,
    )
    steps.append(_step("write_start_record", "kernel.storage.write", start_record))


async def _check_readiness(ctx: AgentContext, task: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    robot = await _call_skill(ctx, steps, "check_robot", "robot.get_state", {})
    if not robot["success"]:
        return _dependency_failure(
            "UNVERIFIED_REAL_DEPENDENCY",
            "robot.get_state did not verify a real robot state backend",
            robot,
            missing=["robot.get_state"],
            next_action="Start the Agentic ROS2 robot state bridge and rerun readiness.",
        )

    arm = await _call_skill(ctx, steps, "check_arm_gripper", "arm.get_state", {})
    if not arm["success"]:
        return _dependency_failure(
            "MANIPULATION_BACKEND_UNAVAILABLE",
            "arm.get_state did not verify the arm and gripper backend",
            arm,
            missing=["arm.get_state", "gripper readiness"],
            next_action="Start the Agentic manipulation bridge and confirm arm and gripper readiness.",
        )

    state = _nested_data(arm).get("state", {})
    readiness = str(state.get("readiness", "")).lower()
    gripper_ready = bool(state.get("gripper_ready", False))
    if readiness in {"backend_unavailable", "unavailable"} or not gripper_ready:
        return {
            "success": False,
            "error_code": "MANIPULATION_BACKEND_UNAVAILABLE",
            "reason": "arm state did not report a ready gripper backend",
            "missing": ["gripper.set backend"],
            "next_action": "Connect the gripper bridge and verify arm.get_state reports gripper_ready.",
            "source_step": arm,
        }
    prepare = await _call_skill(
        ctx,
        steps,
        "prepare_arm_pose",
        "arm.move_named",
        {"name": "arm_home", "timeout_s": min(int(task["timeout_s"]), 8), "_kernel_timeout_s": 20},
    )
    if not prepare["success"]:
        return _dependency_failure(
            "MANIPULATION_BACKEND_UNAVAILABLE",
            "arm_home preparation pose did not complete before color-block detection",
            prepare,
            missing=["arm.move_named arm_home"],
            next_action="Verify the Agentic manipulation bridge can execute the allowlisted arm_home action.",
        )
    align = await _call_skill(
        ctx,
        steps,
        "center_color_block",
        "perception.center_color_block",
        {
            "color": task["color"],
            "target": task["target"],
            "evidence_label": f"{task['evidence_label']}_center",
            "timeout_s": min(int(task["timeout_s"]), 12),
            "_kernel_timeout_s": min(max(int(task["timeout_s"]), 30), 45),
        },
    )
    if not align["success"]:
        code = str(align.get("error_code") or "COLOR_BLOCK_ALIGNMENT_FAILED")
        return _dependency_failure(
            code,
            "color block could not be centered before grasp planning",
            align,
            missing=["perception.center_color_block"],
            next_action="Center the target color block in the camera view through the Agentic perception bridge before pick planning.",
        )
    return {"success": True, "task": task}


async def _confirm_manipulation(ctx: AgentContext, task: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    if not task["require_confirmation"]:
        steps.append(
            {
                "name": "human_confirmation",
                "skill": "human.ask",
                "success": True,
                "skipped": True,
                "error_code": "",
                "reason": "",
                "data": {"require_confirmation": False},
                "syscall_id": "",
                "audit_id": "",
            }
        )
        return {"success": True}
    if bool(task.get("operator_confirmed")):
        steps.append(
            {
                "name": "human_confirmation",
                "skill": "operator.confirmation",
                "success": True,
                "skipped": False,
                "error_code": "",
                "reason": "",
                "data": {
                    "answer": CONFIRM_ANSWER,
                    "require_confirmation": True,
                    "source": str(task.get("operator_confirmation_source") or "cli_yes_flag"),
                },
                "syscall_id": "",
                "audit_id": "",
            }
        )
        return {"success": True}
    question = (
        f"Confirm real manipulation: detect and pick the {task['color']} block, "
        f"then place it at {task['place_target']}."
    )
    confirmation = await _call_skill(
        ctx,
        steps,
        "human_confirmation",
        "human.ask",
        {
            "question": question,
            "options": [CONFIRM_ANSWER, "CANCEL"],
            "timeout_s": min(int(task["timeout_s"]), 60),
            "require_confirmation": True,
        },
    )
    if not confirmation["success"]:
        return _dependency_failure(
            "COLOR_BLOCK_CONFIRMATION_REQUIRED",
            "human confirmation did not complete",
            confirmation,
            missing=["human.ask confirmation"],
            next_action="Answer the human queue confirmation request before rerunning real manipulation.",
        )
    answer = str(_nested_data(confirmation).get("answer", "")).strip().upper()
    if answer != CONFIRM_ANSWER:
        return {
            "success": False,
            "error_code": "COLOR_BLOCK_CONFIRMATION_REQUIRED",
            "reason": "operator did not confirm real manipulation",
            "missing": ["explicit operator confirmation"],
            "next_action": "Rerun and answer CONFIRM when the workspace is safe.",
            "source_step": confirmation,
        }
    return {"success": True}


async def _detect_color_block(ctx: AgentContext, task: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    detection = await _call_skill(
        ctx,
        steps,
        "detect_color_block",
        "perception.detect_color_block",
        {
            "color": task["color"],
            "target": task["target"],
            "evidence_label": task["evidence_label"],
            "timeout_s": min(int(task["timeout_s"]), 30),
            "_kernel_timeout_s": min(max(int(task["timeout_s"]), 45), 75),
        },
    )
    if detection["success"]:
        normalized = _normalized_detection_data(detection)
        validation = _validate_detection_data(task, normalized)
        if not validation["success"]:
            return _dependency_failure(
                "COLOR_BLOCK_DETECTION_INVALID",
                str(validation["reason"]),
                detection,
                missing=list(validation["missing"]),
                next_action="Verify the perception bridge returns color, center_px, confidence, and camera_position_m for the detected block.",
            )
        detection["data"]["validated_detection"] = normalized
        return detection
    raw_code = str(detection.get("error_code") or "")
    if raw_code == "COLOR_BLOCK_NOT_FOUND":
        code = "COLOR_BLOCK_NOT_FOUND"
    elif raw_code in {"ROS_BRIDGE_UNAVAILABLE", "ROS_SERVICE_UNAVAILABLE", "SKILL_BACKEND_UNAVAILABLE", "BACKEND_UNAVAILABLE", "SKILL_NOT_FOUND"}:
        code = "COLOR_BLOCK_CAPABILITY_UNAVAILABLE"
    else:
        code = "COLOR_BLOCK_CAPABILITY_UNAVAILABLE"
    return _dependency_failure(
        code,
        "real color block detection backend is unavailable or did not return a verified detection",
        detection,
        missing=["perception.detect_color_block"],
        next_action="Expose /agentic/perception/detect_color_block through the Agentic perception bridge.",
    )


async def _capture_evidence(ctx: AgentContext, task: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = await _call_skill(
        ctx,
        steps,
        "capture_evidence",
        "perception.capture_photo",
        {
            "target": task["target"],
            "label": task["evidence_label"],
            "timeout_s": 15,
        },
    )
    if evidence["success"]:
        return evidence
    return _dependency_failure(
        "UNVERIFIED_REAL_DEPENDENCY",
        "photo evidence capture backend is unavailable",
        evidence,
        missing=["perception.capture_photo"],
        next_action="Start the Agentic camera bridge and verify capture_photo before manipulation.",
    )


async def _pick_color_block(
    ctx: AgentContext,
    task: dict[str, Any],
    detection: dict[str, Any],
    evidence: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    pick = await _call_skill(
        ctx,
        steps,
        "pick_color_block",
        "manipulation.pick_color_block",
        {
            "color": task["color"],
            "target": task["target"],
            "detection": _normalized_detection_data(detection),
            "evidence": _nested_data(evidence),
            "timeout_s": min(int(task["timeout_s"]), 60),
        },
    )
    if pick["success"]:
        return pick
    raw_code = str(pick.get("error_code") or "")
    code = "MANIPULATION_BACKEND_UNAVAILABLE" if raw_code in {"ROS_BRIDGE_UNAVAILABLE", "ROS_ACTION_UNAVAILABLE", "ROS_SERVICE_UNAVAILABLE", "SKILL_BACKEND_UNAVAILABLE", "BACKEND_UNAVAILABLE", "SKILL_NOT_FOUND"} else "COLOR_BLOCK_PICK_FAILED"
    return _dependency_failure(
        code,
        "real color block pick backend is unavailable or failed",
        pick,
        missing=["manipulation.pick_color_block"],
        next_action="Expose /agentic/manipulation/pick_color_block through the Agentic manipulation bridge.",
    )


async def _place_color_block(ctx: AgentContext, task: dict[str, Any], pick: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    place = await _call_skill(
        ctx,
        steps,
        "place_color_block",
        "manipulation.place_color_block",
        {
            "color": task["color"],
            "place_target": task["place_target"],
            "pick_result": _nested_data(pick),
            "timeout_s": min(int(task["timeout_s"]), 60),
        },
    )
    if place["success"]:
        return place
    raw_code = str(place.get("error_code") or "")
    code = "MANIPULATION_BACKEND_UNAVAILABLE" if raw_code in {"ROS_BRIDGE_UNAVAILABLE", "ROS_ACTION_UNAVAILABLE", "ROS_SERVICE_UNAVAILABLE", "SKILL_BACKEND_UNAVAILABLE", "BACKEND_UNAVAILABLE", "SKILL_NOT_FOUND"} else "COLOR_BLOCK_PLACE_FAILED"
    return _dependency_failure(
        code,
        "real color block place backend is unavailable or failed",
        place,
        missing=["manipulation.place_color_block"],
        next_action="Expose /agentic/manipulation/place_color_block through the Agentic manipulation bridge.",
    )


async def _post_pick_verify(
    ctx: AgentContext,
    task: dict[str, Any],
    detection: dict[str, Any],
    pick: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    gripper_state = await _call_skill(ctx, steps, "post_pick_gripper_state", "arm.get_state", {})
    if not gripper_state["success"]:
        return _dependency_failure(
            "COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE",
            "arm/gripper state could not be read for post-pick verification",
            gripper_state,
            missing=["arm.get_state"],
            next_action="Expose arm.get_state with gripper status before accepting a color-block pick result.",
        )

    post_pick_evidence = await _call_skill(
        ctx,
        steps,
        "capture_post_pick_evidence",
        "perception.capture_photo",
        {
            "target": task["target"],
            "label": f"{task['evidence_label']}_post_pick",
            "timeout_s": 15,
        },
    )
    if not post_pick_evidence["success"]:
        return _dependency_failure(
            "COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE",
            "post-pick photo evidence capture backend is unavailable",
            post_pick_evidence,
            missing=["perception.capture_photo"],
            next_action="Start the Agentic camera bridge and capture post-pick evidence before accepting a pick.",
        )

    verification = await _call_skill(
        ctx,
        steps,
        "post_pick_verify",
        "perception.verify_held_color_block",
        {
            "color": task["color"],
            "target": task["target"],
            "detection": _normalized_detection_data(detection),
            "pick_result": _nested_data(pick),
            "evidence_label": f"{task['evidence_label']}_held_verify",
            "timeout_s": min(int(task["timeout_s"]), 30),
        },
    )
    if verification["success"]:
        validation = _validate_held_verification_data(task, verification)
        if validation["success"]:
            await asyncio.sleep(HOLD_STABILITY_DELAY_S)
            stability_evidence = await _call_skill(
                ctx,
                steps,
                "capture_post_pick_stability_evidence",
                "perception.capture_photo",
                {
                    "target": task["target"],
                    "label": f"{task['evidence_label']}_post_pick_stability",
                    "timeout_s": 15,
                },
            )
            if not stability_evidence["success"]:
                return _dependency_failure(
                    "COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE",
                    "post-pick stability photo evidence capture backend is unavailable",
                    stability_evidence,
                    missing=["perception.capture_photo"],
                    next_action="Capture delayed post-pick evidence before accepting a held color-block result.",
                )
            stability_verification = await _call_skill(
                ctx,
                steps,
                "post_pick_stability_verify",
                "perception.verify_held_color_block",
                {
                    "color": task["color"],
                    "target": task["target"],
                    "detection": _normalized_detection_data(detection),
                    "pick_result": _nested_data(pick),
                    "evidence_label": f"{task['evidence_label']}_held_stability_verify",
                    "timeout_s": min(int(task["timeout_s"]), 30),
                },
            )
            stability_validation = _validate_held_verification_data(task, stability_verification)
            if not stability_verification["success"] or not stability_validation["success"]:
                return _dependency_failure(
                    "COLOR_BLOCK_PICK_VERIFICATION_FAILED",
                    "delayed post-pick verification did not prove the block remained held",
                    stability_verification,
                    missing=list(stability_validation.get("missing") or ["stable verified_held"]),
                    next_action="Tighten the gripper or adjust the pick pose until the target block remains held after a delay.",
                )
            verification["data"]["post_pick_evidence"] = _nested_data(post_pick_evidence)
            verification["data"]["post_pick_gripper_state"] = _nested_data(gripper_state)
            verification["data"]["post_pick_stability_evidence"] = _nested_data(stability_evidence)
            verification["data"]["post_pick_stability_verification"] = _post_pick_verification_data(stability_verification)
            verification["data"]["verified_held"] = True
            return verification
        return _dependency_failure(
            "COLOR_BLOCK_PICK_VERIFICATION_FAILED",
            str(validation["reason"]),
            verification,
            missing=list(validation["missing"]),
            next_action="Adjust the post-pick verification pose/ROI or rerun pick until the target block is visibly held.",
        )

    raw_code = str(verification.get("error_code") or "")
    unavailable_codes = {
        "COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE",
        "ROS_BRIDGE_UNAVAILABLE",
        "ROS_SERVICE_UNAVAILABLE",
        "SKILL_BACKEND_UNAVAILABLE",
        "BACKEND_UNAVAILABLE",
        "SKILL_NOT_FOUND",
    }
    code = "COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE" if raw_code in unavailable_codes else "COLOR_BLOCK_PICK_VERIFICATION_FAILED"
    return _dependency_failure(
        code,
        "post-pick independent verification did not prove the color block is held in the gripper",
        verification,
        missing=["perception.verify_held_color_block"],
        next_action="Capture post-pick evidence and verify the target color appears in the gripper-held ROI before declaring success.",
    )


async def _finish_success(
    ctx: AgentContext,
    task: dict[str, Any],
    detection: dict[str, Any],
    evidence: dict[str, Any],
    pick: dict[str, Any],
    post_pick_verification: dict[str, Any],
    place: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    post_pick_payload = _post_pick_verification_data(post_pick_verification)
    result = _result_payload(ctx, True, task, steps, "", "")
    result.update(
        {
            "detection": _normalized_detection_data(detection),
            "evidence": _nested_data(evidence),
            "pick": _nested_data(pick),
            "post_pick_evidence": dict(post_pick_payload.get("post_pick_evidence") or {}),
            "post_pick_gripper_state": dict(post_pick_payload.get("post_pick_gripper_state") or {}),
            "post_pick_stability_evidence": dict(post_pick_payload.get("post_pick_stability_evidence") or {}),
            "post_pick_stability_verification": dict(post_pick_payload.get("post_pick_stability_verification") or {}),
            "post_pick_verification": post_pick_payload,
            "verified_held": True,
            "place": _nested_data(place),
        }
    )
    await _persist_result(ctx, result, steps)
    report = await _call_skill(
        ctx,
        steps,
        "report_result",
        "report.say",
        {"message": f"Color block task completed for {task['color']} -> {task['place_target']}."},
    )
    if not report["success"]:
        result = _result_payload(ctx, False, task, steps, "SKILL_BACKEND_UNAVAILABLE", "report.say backend unavailable")
    else:
        result = _result_payload(ctx, True, task, steps, "", "")
    result.update(
        {
            "detection": _normalized_detection_data(detection),
            "evidence": _nested_data(evidence),
            "pick": _nested_data(pick),
            "post_pick_evidence": dict(post_pick_payload.get("post_pick_evidence") or {}),
            "post_pick_gripper_state": dict(post_pick_payload.get("post_pick_gripper_state") or {}),
            "post_pick_stability_evidence": dict(post_pick_payload.get("post_pick_stability_evidence") or {}),
            "post_pick_stability_verification": dict(post_pick_payload.get("post_pick_stability_verification") or {}),
            "post_pick_verification": post_pick_payload,
            "verified_held": True,
            "place": _nested_data(place),
        }
    )
    return result


async def _finish_failure(ctx: AgentContext, task: dict[str, Any], steps: list[dict[str, Any]], failure: dict[str, Any]) -> dict[str, Any]:
    result = _result_payload(
        ctx,
        False,
        task,
        steps,
        str(failure.get("error_code") or "UNVERIFIED_REAL_DEPENDENCY"),
        str(failure.get("reason") or "real dependency is unavailable"),
        missing=list(failure.get("missing") or []),
        next_action=str(failure.get("next_action") or "Configure the real backend and rerun."),
    )
    result.update(_post_pick_failure_payload(steps))
    await _persist_result(ctx, result, steps)
    report = await _call_skill(
        ctx,
        steps,
        "report_failure",
        "report.say",
        {"message": f"Color block task did not run: {result['error_code']}."},
    )
    if not report["success"]:
        result["report_error_code"] = report.get("error_code", "")
    result["steps"] = steps
    result["syscall_ids"] = [step["syscall_id"] for step in steps if step.get("syscall_id")]
    result["audit_ids"] = [step["audit_id"] for step in steps if step.get("audit_id")]
    return result


async def _persist_result(ctx: AgentContext, result: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    memory = await ctx.kernel.memory.remember(
        result,
        key=f"{ctx.session_id}:color-block-result",
        tags=["color_block", "evidence"],
        timeout_s=5,
    )
    steps.append(_step("remember_result", "kernel.memory.remember", memory))
    storage = await ctx.kernel.storage.write(
        f"color_block_grasper_agent/{ctx.session_id}_result.json",
        result,
        timeout_s=5,
    )
    steps.append(_step("write_result", "kernel.storage.write", storage))


async def _call_skill(
    ctx: AgentContext,
    steps: list[dict[str, Any]],
    name: str,
    skill_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    call_args = dict(args)
    kernel_timeout_s = int(call_args.pop("_kernel_timeout_s", call_args.get("timeout_s") or 10))
    result = await ctx.kernel.skill.call(skill_name, call_args, timeout_s=kernel_timeout_s)
    step = _step(name, skill_name, result)
    steps.append(step)
    return step


def _dependency_failure(
    error_code: str,
    reason: str,
    source_step: dict[str, Any],
    *,
    missing: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": error_code,
        "reason": reason,
        "missing": missing,
        "next_action": next_action,
        "source_step": source_step,
    }


def _result_payload(
    ctx: AgentContext,
    success: bool,
    task: dict[str, Any],
    steps: list[dict[str, Any]],
    error_code: str,
    reason: str,
    *,
    missing: list[str] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "success": success,
        "app_id": ctx.app_manifest.name or APP_ID,
        "planner_mode": str(task.get("planner_mode") or ""),
        "task_text": str(task.get("task_text") or ""),
        "plan": dict(task.get("plan") or {}),
        "task": task,
        "steps": steps,
        "error_code": error_code,
        "reason": reason,
        "missing": list(missing or []),
        "next_action": next_action,
        "syscall_ids": [step["syscall_id"] for step in steps if step.get("syscall_id")],
        "audit_ids": [step["audit_id"] for step in steps if step.get("audit_id")],
    }


def _llm_step(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "skill": "ctx.llm.chat_json",
        "success": bool(result["success"]),
        "error_code": str(result.get("error_code") or ""),
        "reason": str(result.get("reason") or ""),
        "syscall_id": "",
        "audit_id": "",
        "data": {"plan": dict(result.get("plan") or {}), "metadata": dict(result.get("metadata") or {})},
    }


def _plan_validation_step(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "validate_plan",
        "skill": "deterministic.schema",
        "success": bool(validation["success"]),
        "error_code": str(validation.get("error_code") or ""),
        "reason": str(validation.get("reason") or ""),
        "syscall_id": "",
        "audit_id": "",
        "data": {"planner_mode": "llm"},
    }


def _step(name: str, skill: str, result: Any) -> dict[str, Any]:
    summary = _result_summary(result)
    return {"name": name, "skill": skill, **summary}


def _result_summary(result: Any) -> dict[str, Any]:
    response = getattr(result, "response", None)
    payload = _response_payload(response)
    nested = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    error_code = str(getattr(result, "error_code", "") or payload.get("error_code") or nested.get("error_code") or "")
    reason = str(payload.get("reason") or nested.get("reason") or "")
    audit_id = str(getattr(result, "audit_id", "") or payload.get("audit_id") or nested.get("audit_id") or "")
    return {
        "success": bool(getattr(result, "success", False)),
        "error_code": error_code,
        "reason": reason,
        "syscall_id": str(getattr(result, "syscall_id", "") or ""),
        "audit_id": audit_id,
        "data": payload,
    }


def _response_payload(response: Any) -> dict[str, Any]:
    data = getattr(response, "data", None)
    if isinstance(data, dict) and data:
        return dict(data)
    metadata = getattr(response, "metadata", None)
    if isinstance(metadata, dict) and metadata:
        return dict(metadata)
    if isinstance(response, dict):
        return dict(response)
    return {}


def _normalized_detection_data(step: dict[str, Any]) -> dict[str, Any]:
    data = _nested_data(step)
    candidates = [
        data.get("detection") if isinstance(data.get("detection"), dict) else {},
        data.get("evidence") if isinstance(data.get("evidence"), dict) else {},
        data,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and _looks_like_color_block_detection(candidate):
            return dict(candidate)
    return {}


def _looks_like_color_block_detection(payload: dict[str, Any]) -> bool:
    return bool(
        payload
        and (
            payload.get("kind") == "color_block_detection"
            or payload.get("detection_id")
            or payload.get("camera_position_m")
        )
    )


def _validate_detection_data(task: dict[str, Any], detection: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    if not detection:
        return {"success": False, "reason": "color block detection payload is empty", "missing": ["detection"]}
    if str(detection.get("color") or "").lower() != str(task["color"]).lower():
        return {"success": False, "reason": "detected color does not match LLM plan target_color", "missing": ["matching color"]}
    camera_position = detection.get("camera_position_m")
    if not isinstance(camera_position, list) or len(camera_position) < 3:
        missing.append("camera_position_m")
    center_px = detection.get("center_px")
    if not isinstance(center_px, list) or len(center_px) < 2:
        missing.append("center_px")
    if "confidence" not in detection:
        missing.append("confidence")
    if missing:
        return {"success": False, "reason": "color block detection payload lacks fields required for pick", "missing": missing}
    return {"success": True, "reason": "", "missing": []}


def _validate_held_verification_data(task: dict[str, Any], verification_step: dict[str, Any]) -> dict[str, Any]:
    data = _nested_data(verification_step)
    verification = data.get("verification") if isinstance(data.get("verification"), dict) else {}
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    verified_held = bool(data.get("verified_held") or verification.get("verified_held") or evidence.get("verified_held"))
    missing: list[str] = []
    if not verified_held:
        missing.append("verified_held")
    color = str(verification.get("target_color") or evidence.get("color") or "").lower()
    if color != str(task["color"]).lower():
        missing.append("matching target_color")
    if not isinstance(verification.get("candidate"), dict) or not verification.get("candidate"):
        missing.append("held color candidate")
    size_confirms_lift = bool(verification.get("size_confirms_lift") or evidence.get("size_confirms_lift"))
    if not size_confirms_lift:
        missing.append("size_confirms_lift")
    overlaps_pre_pick = verification.get("overlaps_pre_pick_detection")
    if overlaps_pre_pick is None:
        overlaps_pre_pick = evidence.get("overlaps_pre_pick_detection")
    if overlaps_pre_pick is not False:
        missing.append("no pre-pick overlap")
    try:
        radius_ratio = float(verification.get("radius_ratio_vs_pre_pick") or evidence.get("radius_ratio_vs_pre_pick") or 0.0)
        min_radius_ratio = float(
            verification.get("min_radius_ratio_vs_pre_pick") or evidence.get("min_radius_ratio_vs_pre_pick") or 1.0
        )
    except (TypeError, ValueError):
        radius_ratio = 0.0
        min_radius_ratio = 1.0
    if radius_ratio < min_radius_ratio:
        missing.append("radius ratio confirms lift")
    position_confirms_gripper_roi = bool(
        verification.get("position_confirms_gripper_roi") or evidence.get("position_confirms_gripper_roi")
    )
    if not position_confirms_gripper_roi:
        missing.append("position_confirms_gripper_roi")
    if not str(verification.get("evidence_image_path") or evidence.get("debug_image_path") or ""):
        missing.append("post-pick verification image")
    if not str(verification.get("evidence_metadata_path") or evidence.get("metadata_path") or ""):
        missing.append("post-pick verification metadata")
    if missing:
        return {
            "success": False,
            "reason": "post-pick verification did not independently prove the target block is held",
            "missing": missing,
        }
    return {"success": True, "reason": "", "missing": []}


def _nested_data(step: dict[str, Any]) -> dict[str, Any]:
    data = step.get("data")
    if not isinstance(data, dict):
        return {}
    nested = data.get("result")
    if isinstance(nested, dict):
        nested_data = nested.get("data")
        if isinstance(nested_data, dict):
            return dict(nested_data)
        return dict(nested)
    return dict(data)


def _post_pick_verification_data(step: dict[str, Any]) -> dict[str, Any]:
    payload = _nested_data(step)
    data = step.get("data")
    if isinstance(data, dict):
        for key in (
            "post_pick_evidence",
            "post_pick_gripper_state",
            "post_pick_stability_evidence",
            "post_pick_stability_verification",
            "verified_held",
        ):
            if key in data:
                payload[key] = data[key]
    return payload


def _post_pick_failure_payload(steps: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {str(step.get("name") or ""): step for step in steps}
    payload: dict[str, Any] = {}
    if "capture_post_pick_evidence" in by_name:
        payload["post_pick_evidence"] = _nested_data(by_name["capture_post_pick_evidence"])
    if "post_pick_gripper_state" in by_name:
        payload["post_pick_gripper_state"] = _nested_data(by_name["post_pick_gripper_state"])
    if "post_pick_verify" in by_name:
        payload["post_pick_verification"] = _post_pick_verification_data(by_name["post_pick_verify"])
        payload["verified_held"] = False
    if "capture_post_pick_stability_evidence" in by_name:
        payload["post_pick_stability_evidence"] = _nested_data(by_name["capture_post_pick_stability_evidence"])
    if "post_pick_stability_verify" in by_name:
        payload["post_pick_stability_verification"] = _post_pick_verification_data(by_name["post_pick_stability_verify"])
    return payload
