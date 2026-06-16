from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from agentic_runtime.llm import LLMError, OpenAICompatibleChatClient
from agentic_runtime.types import new_id


APP_DIR = Path(__file__).resolve().parent
CAMERA_POSE_ACTIONS = [
    "camera_center",
    "camera_yaw_left_15",
    "camera_yaw_right_15",
    "camera_pitch_up_15",
]
ARM_ACTIONS = ["arm_home", *CAMERA_POSE_ACTIONS]


def plan_task(task_input: Any) -> dict[str, Any]:
    task = _normalize_task(task_input)
    if _llm_planning_enabled():
        try:
            return _plan_task_with_llm(task)
        except LLMError:
            pass
        except (ValidationError, OSError, json.JSONDecodeError):
            pass
    return _rule_plan_task(task)


def _plan_task_with_llm(task: dict[str, Any]) -> dict[str, Any]:
    text = str(task.get("text", "")).strip()
    if not text:
        raise LLMError("LLM_INPUT_EMPTY", "empty task text")
    client = OpenAICompatibleChatClient()
    plan = client.chat_json(system_prompt=_load_system_prompt(), user_prompt=_build_user_prompt(text))
    Draft202012Validator(_load_plan_schema()).validate(plan)
    if plan.get("planner_mode") != "llm":
        raise LLMError("LLM_PLAN_MODE_INVALID", "LLM plan must use planner_mode=llm")
    return plan


def _rule_plan_task(task_input: Any) -> dict[str, Any]:
    task = _normalize_task(task_input)
    text = str(task.get("text", "")).strip()
    compact = re.sub(r"\s+", "", text.lower())
    target = "workspace"

    if not text:
        return _plan("unsupported", "read_only", False, False, [], "没有收到任务文本")

    if _has_any(compact, text, ["停止", "取消", "别动了", "stop", "cancel"]):
        return _plan(
            "stop",
            "emergency_control",
            False,
            False,
            [{"type": "stop", "reason": "operator_requested_from_robot_photographer"}],
            "停止当前机器人动作",
            target=target,
        )

    if _has_any(compact, text, ["状态", "ready", "status", "state"]):
        return _plan("status", "read_only", False, False, [{"type": "status"}], "查看机器人和机械臂状态", target=target)

    if _has_any(compact, text, ["最近照片", "上一张", "拍了什么", "recent"]):
        return _plan("recent_photos", "read_only", False, False, [{"type": "recent_photos", "limit": 5}], "查看最近照片", target=target)

    if _requests_unsupported_pitch_down(compact, text):
        return _plan(
            "unsupported",
            "read_only",
            False,
            False,
            [{"type": "status"}],
            "向下俯仰拍摄暂不支持：尚未验证安全的 camera_pitch_down 后端动作",
            target=target,
        )

    if _has_any(compact, text, ["回到初始", "回安全位", "armhome", "home"]):
        return _plan(
            "arm_home",
            "named_motion",
            True,
            True,
            [{"type": "arm_named_action", "name": "arm_home", "timeout_s": 8}],
            "机械臂回到初始位",
            target=target,
        )

    if _requests_multi_angle(compact, text):
        poses = _multi_angle_poses(compact, text)
        verify = _has_any(compact, text, ["验证", "确认", "不一样", "不同", "差异", "verify"]) or len(poses) > 1
        return _multi_angle_plan(poses, verify=verify, target=target)

    if _has_any(compact, text, ["前后", "前后对比", "对比", "beforeafter", "before and after"]) and _has_any(
        compact, text, ["拍", "照片", "photo", "capture"]
    ):
        return _plan(
            "before_after_capture",
            "named_motion",
            True,
            True,
            [
                {"type": "capture_photo", "target": target, "label": "before", "timeout_s": 5},
                {"type": "arm_named_action", "name": "camera_pitch_up_15", "timeout_s": 8},
                {"type": "capture_photo", "target": target, "label": "after_pitch_up_15", "timeout_s": 5},
            ],
            "先拍一张，再抬起相机拍一张对比照片",
            target=target,
        )

    if _has_any(compact, text, ["抬起", "抬高", "cameraup", "raise"]):
        return _plan(
            "move_camera_pose",
            "named_motion",
            True,
            True,
            [
                {"type": "arm_named_action", "name": "camera_pitch_up_15", "timeout_s": 8},
                {"type": "capture_photo", "target": target, "label": "after_pitch_up_15", "timeout_s": 5},
            ],
            "抬起相机后拍摄一张工作区照片",
            target=target,
        )

    if _has_any(compact, text, ["连拍", "连续", "三张", "3张", "burst"]):
        count = _extract_count(text, default=3)
        steps: list[dict[str, Any]] = []
        for idx in range(count):
            steps.append({"type": "capture_photo", "target": target, "label": f"photo_{idx + 1:03d}", "timeout_s": 5})
            if idx != count - 1:
                steps.append({"type": "sleep", "duration_s": 0.5})
        return _plan("capture_burst", "read_only", False, False, steps, f"连续拍摄 {count} 张工作区照片", target=target)

    if _has_any(compact, text, ["拍", "照片", "图片", "看一下", "看看", "photo", "picture", "image"]):
        return _plan(
            "capture_photo",
            "read_only",
            False,
            False,
            [{"type": "capture_photo", "target": target, "label": "photo", "timeout_s": 5}],
            "拍摄一张工作区照片",
            target=target,
        )

    return _plan("unsupported", "read_only", False, False, [{"type": "status"}], "暂不支持该摄影任务", target=target)


def _llm_planning_enabled() -> bool:
    return os.environ.get("AGENTIC_LLM_ENABLED") == "1"


def _load_system_prompt() -> str:
    return (APP_DIR / "prompts" / "intent_parser.system.md").read_text(encoding="utf-8")


def _load_plan_schema() -> dict[str, Any]:
    return json.loads((APP_DIR / "schemas" / "photo_plan.schema.json").read_text(encoding="utf-8"))


def _build_user_prompt(text: str) -> str:
    return json.dumps(
        {
            "task": text,
            "required_plan_id": new_id("plan"),
            "target_allowlist": ["workspace"],
            "arm_action_allowlist": ARM_ACTIONS,
            "multi_angle_camera_poses": CAMERA_POSE_ACTIONS,
            "allowed_intents": [
                "capture_photo",
                "capture_burst",
                "move_camera_pose",
                "arm_home",
                "before_after_capture",
                "multi_angle_capture",
                "verify_photo_differences",
                "recent_photos",
                "status",
                "stop",
                "unsupported",
            ],
            "max_capture_count": 5,
            "max_capture_timeout_s": 5,
            "max_arm_timeout_s": 8,
            "max_sleep_s": 5,
            "output_contract": (
                "Return one raw JSON object compatible with photo_plan.schema.json. "
                "Use required_plan_id exactly as plan_id. Include user_summary. "
                "Every capture_photo step must include target, label, and timeout_s. "
                "Every arm_named_action step must include name and timeout_s."
            ),
        },
        ensure_ascii=False,
    )


def _normalize_task(task_input: Any) -> dict[str, Any]:
    if isinstance(task_input, dict):
        data = dict(task_input)
        if "text" not in data and "task" in data:
            data["text"] = data["task"]
        return data
    return {"text": str(task_input)}


def _plan(
    intent: str,
    risk_class: str,
    requires_motion: bool,
    needs_confirmation: bool,
    steps: list[dict[str, Any]],
    summary: str,
    target: str = "workspace",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "plan_id": new_id("plan"),
        "intent": intent,
        "risk_class": risk_class,
        "requires_motion": requires_motion,
        "needs_confirmation": needs_confirmation,
        "planner_mode": "rule_based",
        "target": target,
        "steps": steps,
        "user_summary": summary,
    }


def _multi_angle_poses(compact: str, raw: str) -> list[str]:
    poses: list[str] = []
    if _has_any(compact, raw, ["回中", "中间", "中心", "center"]):
        poses.append("camera_center")
    if _has_any(compact, raw, ["左右", "左边右边", "左转右转", "yaw"]):
        poses.extend(["camera_yaw_left_15", "camera_yaw_right_15"])
    else:
        if _has_any(compact, raw, ["左", "left"]):
            poses.append("camera_yaw_left_15")
        if _has_any(compact, raw, ["右", "right"]):
            poses.append("camera_yaw_right_15")
    if _has_any(compact, raw, ["上", "抬高", "up", "pitch up"]):
        poses.append("camera_pitch_up_15")
    if not poses or _has_any(compact, raw, ["多角度", "不同角度", "一组角度", "multiangle", "multi-angle"]):
        poses = list(CAMERA_POSE_ACTIONS)
    return list(dict.fromkeys(poses))[:5]


def _multi_angle_plan(poses: list[str], *, verify: bool, target: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for pose in poses:
        steps.append({"type": "arm_named_action", "name": pose, "timeout_s": 8})
        steps.append({"type": "capture_photo", "target": target, "label": pose.replace("camera_", ""), "timeout_s": 5})
    if verify:
        steps.append({"type": "verify_photo_differences", "method": "deterministic_cv_metrics", "min_difference_score": 0.08})
    steps.append({"type": "arm_named_action", "name": "arm_home", "timeout_s": 8})
    return _plan(
        "multi_angle_capture",
        "named_motion",
        True,
        True,
        steps,
        "从多个受控相机角度拍摄工作区并验证差异" if verify else "从多个受控相机角度拍摄工作区",
        target=target,
    )


def _has_any(compact: str, raw: str, tokens: list[str]) -> bool:
    lowered = raw.lower()
    return any(token.lower().replace(" ", "") in compact or token.lower() in lowered for token in tokens)


def _requests_unsupported_pitch_down(compact: str, raw: str) -> bool:
    return _has_any(compact, raw, ["向下", "下拍", "降低", "上下", "俯仰", "pitchdown", "pitch down"])


def _requests_multi_angle(compact: str, raw: str) -> bool:
    if _has_any(compact, raw, ["多角度", "不同角度", "一组角度", "左右", "multiangle", "multi-angle"]):
        return True
    wants_photo = _has_any(compact, raw, ["拍", "照片", "图片", "photo", "picture", "image"])
    has_left = _has_any(compact, raw, ["左边", "左侧", "向左", "left"])
    has_right = _has_any(compact, raw, ["右边", "右侧", "向右", "right"])
    has_center = _has_any(compact, raw, ["中间", "中心", "正中", "center"])
    has_up = _has_any(compact, raw, ["上面", "上方", "抬高", "向上", "up", "pitch up"])
    return wants_photo and ((has_left and has_right) or (has_center and (has_left or has_right or has_up)))


def _extract_count(text: str, default: int) -> int:
    match = re.search(r"(\d+)\s*张", text)
    if match:
        return int(match.group(1))
    for word, count in {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}.items():
        if f"{word}张" in text or f"{word} 张" in text:
            return count
    return default
