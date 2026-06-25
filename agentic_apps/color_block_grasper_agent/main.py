from __future__ import annotations

from typing import Any

from agentic_runtime.sdk import AgentContext


APP_ID = "color_block_grasper_agent"
PLAN_SCHEMA_VERSION = "1.0"
ALLOWED_COLORS = {"red", "green", "blue", "yellow"}
CONFIRM_ANSWER = "CONFIRM"
PLAN_STEPS = ["detect_color_block", "capture_evidence", "pick_color_block", "place_color_block"]
RISK_CLASSES = {"controlled_manipulation", "manipulation_real_hardware"}


async def run(ctx: AgentContext, **kwargs: Any) -> dict[str, Any]:
    task_text = str(kwargs.get("task_text") or kwargs.get("message") or "").strip()
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

    task = _task_from_plan(task_text, plan)
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

    place = await _place_color_block(ctx, task, pick, steps)
    if not place["success"]:
        return await _finish_failure(ctx, task, steps, place)

    return await _finish_success(ctx, task, detection, evidence, pick, place, steps)


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
            "- place_target: a concrete tray or workspace destination",
            "- requires_manipulation: true",
            "- needs_confirmation: true",
            "- steps: exactly ['detect_color_block','capture_evidence','pick_color_block','place_color_block']",
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


def _task_from_plan(task_text: str, plan: dict[str, Any]) -> dict[str, Any]:
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
    }


def _validate_policy(ctx: AgentContext, task: dict[str, Any]) -> dict[str, Any]:
    required_permissions = [
        "perception.detect.color_block",
        "perception.capture",
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
        },
    )
    if detection["success"]:
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
            "timeout_s": 5,
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
            "detection": _nested_data(detection),
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


async def _finish_success(
    ctx: AgentContext,
    task: dict[str, Any],
    detection: dict[str, Any],
    evidence: dict[str, Any],
    pick: dict[str, Any],
    place: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    result = _result_payload(ctx, True, task, steps, "", "")
    result.update(
        {
            "detection": _nested_data(detection),
            "evidence": _nested_data(evidence),
            "pick": _nested_data(pick),
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
            "detection": _nested_data(detection),
            "evidence": _nested_data(evidence),
            "pick": _nested_data(pick),
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
    result = await ctx.kernel.skill.call(skill_name, args, timeout_s=int(args.get("timeout_s") or 10))
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
