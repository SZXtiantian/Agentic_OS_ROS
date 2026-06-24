from __future__ import annotations

from typing import Any

from agentic_runtime.sdk import AgentContext


APP_ID = "color_block_grasper_agent"
ALLOWED_COLORS = {"red", "green", "blue", "yellow"}
CONFIRM_ANSWER = "CONFIRM"


async def run(ctx: AgentContext, **kwargs: Any) -> dict[str, Any]:
    task_or_error = _normalize_task(kwargs)
    if not task_or_error["success"]:
        return await _finish_failure(ctx, task_or_error["task"], [], task_or_error)

    task = task_or_error["task"]
    steps: list[dict[str, Any]] = []
    await _record_start(ctx, task, steps)

    readiness = await _check_readiness(ctx, task, steps)
    if not readiness["success"]:
        return await _finish_failure(ctx, task, steps, readiness)

    confirmation = await _confirm_manipulation(ctx, task, steps)
    if not confirmation["success"]:
        return await _finish_failure(ctx, task, steps, confirmation)

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


def _normalize_task(kwargs: dict[str, Any]) -> dict[str, Any]:
    color = str(kwargs.get("color") or "red").strip().lower()
    place_target = str(kwargs.get("place_target") or "workspace_drop_zone").strip()
    timeout_s = int(kwargs.get("timeout_s") or 180)
    evidence_label = str(kwargs.get("evidence_label") or f"{color}_block_grasp").strip()
    require_confirmation = bool(kwargs.get("require_confirmation", True))
    task = {
        "color": color,
        "place_target": place_target,
        "require_confirmation": require_confirmation,
        "evidence_label": evidence_label,
        "timeout_s": timeout_s,
        "target": str(kwargs.get("target") or "workspace"),
    }
    if color not in ALLOWED_COLORS:
        return {
            "success": False,
            "task": task,
            "error_code": "COLOR_BLOCK_COLOR_NOT_ALLOWED",
            "reason": f"color must be one of {', '.join(sorted(ALLOWED_COLORS))}",
            "missing": [],
            "next_action": "Choose an allowed color and rerun the app.",
        }
    return {"success": True, "task": task}


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
        "task": task,
        "steps": steps,
        "error_code": error_code,
        "reason": reason,
        "missing": list(missing or []),
        "next_action": next_action,
        "syscall_ids": [step["syscall_id"] for step in steps if step.get("syscall_id")],
        "audit_ids": [step["audit_id"] for step in steps if step.get("audit_id")],
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
