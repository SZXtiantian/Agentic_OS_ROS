from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from agentic_runtime.llm import LLMError
from agentic_runtime.types import new_id

from .app_index import AppIndex, AppIndexEntry
from .errors import DispatchError


DISPATCHER_DIR = Path(__file__).resolve().parent


class DispatcherPlanner:
    def __init__(self, llm_chat: Any | None = None) -> None:
        self.llm_chat = llm_chat

    def plan(self, user_text: str, app_index: AppIndex, flags: Any, *, task_id: str, route_plan_id: str) -> dict[str, Any]:
        require_llm = _require_llm(flags)
        if getattr(flags, "no_llm", False) and require_llm:
            raise DispatchError("DISPATCH_LLM_REQUIRED_BUT_DISABLED", "LLM is required, but --no-llm was provided")
        if self.llm_chat is not None and not getattr(flags, "no_llm", False) and (
            require_llm or os.environ.get("AGENTIC_LLM_ENABLED") == "1"
        ):
            try:
                plan = self._plan_with_llm(user_text, app_index, flags, task_id=task_id, route_plan_id=route_plan_id)
                plan["fallback"] = {"used": False, "reason": ""}
                return _apply_forced_app(plan, flags, app_index)
            except Exception as exc:
                if require_llm:
                    raise DispatchError(
                        "DISPATCH_LLM_REQUIRED_FAILED",
                        f"required LLM route planning failed: {exc.__class__.__name__}: {str(exc)[:160]}",
                    ) from exc
                fallback = self._rule_plan(user_text, flags, task_id=task_id, route_plan_id=route_plan_id)
                fallback["fallback"] = {"used": True, "reason": f"{exc.__class__.__name__}: {str(exc)[:160]}"}
                return _apply_forced_app(fallback, flags, app_index)
        if require_llm:
            raise DispatchError("DISPATCH_LLMCHAT_UNAVAILABLE", "LLM is required, but AgenticOS LLMChat is unavailable")
        return _apply_forced_app(self._rule_plan(user_text, flags, task_id=task_id, route_plan_id=route_plan_id), flags, app_index)

    def _plan_with_llm(
        self,
        user_text: str,
        app_index: AppIndex,
        flags: Any,
        *,
        task_id: str,
        route_plan_id: str,
    ) -> dict[str, Any]:
        prompt = _build_user_prompt(user_text, app_index, flags, task_id=task_id, route_plan_id=route_plan_id)
        if self.llm_chat is None:
            raise LLMError("LLMCHAT_UNAVAILABLE", "AgenticOS LLMChat service is unavailable")
        plan = self.llm_chat.chat_json(system_prompt=_system_prompt(), user_prompt=prompt)
        plan.setdefault("task_id", task_id)
        plan.setdefault("route_plan_id", route_plan_id)
        plan.setdefault("created_at", _now())
        plan.setdefault("user_text", user_text)
        plan.setdefault("fallback", {"used": False, "reason": ""})
        Draft202012Validator(_schema()).validate(plan)
        if plan.get("planner_mode") != "llm":
            raise LLMError("LLM_PLAN_MODE_INVALID", "dispatcher LLM plan must use planner_mode=llm")
        app_task_input = dict(plan.get("app_task_input") or {})
        app_task_input.setdefault("text", user_text)
        app_task_input["allow_arm_motion"] = bool(getattr(flags, "allow_arm_motion", False))
        app_task_input["assume_yes"] = bool(getattr(flags, "assume_yes", False))
        app_task_input["parent_task_id"] = task_id
        app_task_input["route_plan_id"] = route_plan_id
        if _require_llm(flags):
            app_task_input["require_llm"] = True
        plan["app_task_input"] = app_task_input
        plan = _normalize_indexed_app_route(plan, app_index)
        return plan

    def _rule_plan(self, user_text: str, flags: Any, *, task_id: str, route_plan_id: str) -> dict[str, Any]:
        text = user_text.strip()
        compact = re.sub(r"\s+", "", text.lower())
        base_input = {
            "text": text,
            "allow_arm_motion": bool(getattr(flags, "allow_arm_motion", False)),
            "assume_yes": bool(getattr(flags, "assume_yes", False)),
            "parent_task_id": task_id,
            "route_plan_id": route_plan_id,
            "require_llm": _require_llm(flags),
        }

        if not text:
            return _route(
                task_id,
                route_plan_id,
                text,
                "unsupported",
                "unsupported",
                "unsupported",
                False,
                False,
                {},
                "没有收到任务文本",
                "empty user input",
            )
        if _has_any(compact, text, ["帮助", "help", "?"]):
            return _route(task_id, route_plan_id, text, "help", "builtin.help", "read_only", False, False, {}, "显示帮助", "built-in help")
        if _has_any(compact, text, ["最近任务", "任务记录", "tasks"]):
            return _route(
                task_id,
                route_plan_id,
                text,
                "tasks",
                "builtin.tasks",
                "read_only",
                False,
                False,
                {"limit": int(getattr(flags, "tasks_limit", 20))},
                "查看最近任务",
                "built-in task log query",
            )
        if _has_any(compact, text, ["上一个任务", "上次结果", "lasttask", "last task"]):
            return _route(
                task_id,
                route_plan_id,
                text,
                "last_task",
                "builtin.last_task",
                "read_only",
                False,
                False,
                {},
                "查看上一个任务结果",
                "built-in last task query",
            )
        if _has_any(compact, text, ["停止", "急停", "取消", "stop", "cancel"]):
            return _route(
                task_id,
                route_plan_id,
                text,
                "robot_stop",
                "builtin.stop",
                "emergency_control",
                False,
                False,
                {"reason": "operator_requested_from_dispatcher"},
                "停止机器人",
                "safe built-in stop",
            )
        if _has_any(compact, text, ["状态", "现在情况", "status", "state"]):
            return _route(
                task_id,
                route_plan_id,
                text,
                "robot_status",
                "builtin.status",
                "read_only",
                False,
                False,
                {},
                "查看 AgenticOS 状态",
                "built-in runtime status",
            )
        if _unsafe_down_request(compact, text):
            return _route(
                task_id,
                route_plan_id,
                text,
                "unsupported",
                "unsupported",
                "unsupported",
                False,
                False,
                {},
                "向下俯仰拍摄暂不支持：尚未验证安全后端动作",
                "unsafe downward camera pose",
            )
        if _direct_unsafe_request(compact, text):
            return _route(
                task_id,
                route_plan_id,
                text,
                "unsupported",
                "unsupported",
                "unsupported",
                False,
                False,
                {},
                "请求包含直接机器人中间件或未授权运动控制，已拒绝",
                "unsafe direct control request",
            )
        if _has_any(compact, text, ["最近照片", "照片列表", "拍了什么", "recent photo"]):
            return _route(
                task_id,
                route_plan_id,
                text,
                "recent_photos",
                "robot_photographer_agent",
                "read_only",
                False,
                False,
                base_input,
                "使用 Robot Photographer 查看最近照片",
                "photography task owner",
            )
        if _multi_angle_request(compact, text):
            return _route(
                task_id,
                route_plan_id,
                text,
                "multi_angle_photo",
                "robot_photographer_agent",
                "named_motion",
                True,
                True,
                base_input,
                "使用 Robot Photographer 执行受控多角度拍摄",
                "multi-angle photography task owner",
            )
        if _has_any(compact, text, ["拍照", "照片", "图片", "相机", "看一下", "看看", "photo", "picture", "image", "camera"]):
            return _route(
                task_id,
                route_plan_id,
                text,
                "capture_photo",
                "robot_photographer_agent",
                "read_only",
                False,
                False,
                base_input,
                "使用 Robot Photographer 拍摄一张工作区照片",
                "photography task owner",
            )
        return _route(
            task_id,
            route_plan_id,
            text,
            "unsupported",
            "unsupported",
            "unsupported",
            False,
            False,
            {},
            "暂不支持该自然语言任务",
            "no enabled app route matched",
        )


def _route(
    task_id: str,
    route_plan_id: str,
    user_text: str,
    intent: str,
    selected_app_id: str,
    risk_class: str,
    requires_motion: bool,
    needs_confirmation: bool,
    app_task_input: dict[str, Any],
    summary: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "route_plan_id": route_plan_id,
        "created_at": _now(),
        "user_text": user_text,
        "planner_mode": "rule_based",
        "intent": intent,
        "selected_app_id": selected_app_id,
        "route_reason": reason,
        "risk_class": risk_class,
        "requires_robot_motion": bool(requires_motion),
        "needs_confirmation": bool(needs_confirmation),
        "target": "workspace",
        "app_task_input": app_task_input,
        "preflight_checks": [],
        "fallback": {"used": False, "reason": ""},
        "user_summary": summary,
    }


def _system_prompt() -> str:
    return (DISPATCHER_DIR / "prompts" / "dispatcher.system.md").read_text(encoding="utf-8")


def _schema() -> dict[str, Any]:
    return json.loads((DISPATCHER_DIR / "schemas" / "task_route_plan.schema.json").read_text(encoding="utf-8"))


def _build_user_prompt(user_text: str, app_index: AppIndex, flags: Any, *, task_id: str, route_plan_id: str) -> str:
    app_summaries = app_index.to_prompt_summary()
    return json.dumps(
        {
            "user_text": user_text,
            "required_task_id": task_id,
            "required_route_plan_id": route_plan_id,
            "created_at": _now(),
            "app_index": app_summaries,
            "allowed_selected_app_ids": _allowed_selected_app_ids(app_index),
            "allowed_intents": _allowed_intents(app_index),
            "target_allowlist": _target_allowlist(app_index),
            "flags": {
                "allow_arm_motion": bool(getattr(flags, "allow_arm_motion", False)),
                "assume_yes": bool(getattr(flags, "assume_yes", False)),
                "require_llm": _require_llm(flags),
            },
            "output_contract": (
                "Return exactly one JSON object with every field in output_template. "
                "Use selected_app_id, not app_id. Use planner_mode='llm'. "
                "Do not omit schema_version, created_at, user_text, route_reason, "
                "risk_class, requires_robot_motion, needs_confirmation, app_task_input, "
                "preflight_checks, fallback, or user_summary."
            ),
            "output_template": {
                "schema_version": "1.0",
                "task_id": task_id,
                "route_plan_id": route_plan_id,
                "created_at": "<created_at_iso8601>",
                "user_text": user_text,
                "planner_mode": "llm",
                "intent": "<one allowed intent>",
                "selected_app_id": "<one allowed selected_app_id>",
                "route_reason": "<short routing reason>",
                "risk_class": "<read_only | named_motion | emergency_control | unsupported>",
                "requires_robot_motion": False,
                "needs_confirmation": False,
                "target": "workspace",
                "app_task_input": {
                    "text": user_text,
                    "allow_arm_motion": bool(getattr(flags, "allow_arm_motion", False)),
                    "assume_yes": bool(getattr(flags, "assume_yes", False)),
                    "parent_task_id": task_id,
                    "route_plan_id": route_plan_id,
                    "require_llm": _require_llm(flags),
                },
                "preflight_checks": [],
                "fallback": {"used": False, "reason": ""},
                "user_summary": "<short Chinese summary>",
            },
        },
        ensure_ascii=False,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_llm(flags: Any) -> bool:
    return bool(getattr(flags, "require_llm", False)) or os.environ.get("AGENTIC_LLM_REQUIRE") == "1"


def _allowed_selected_app_ids(app_index: AppIndex) -> list[str]:
    app_ids = [entry.app_id for entry in app_index.enabled_entries()]
    return list(
        dict.fromkeys(
            [
                *app_ids,
                "builtin.status",
                "builtin.stop",
                "builtin.tasks",
                "builtin.last_task",
                "builtin.help",
                "unsupported",
            ]
        )
    )


def _allowed_intents(app_index: AppIndex) -> list[str]:
    intents: list[str] = []
    for entry in app_index.enabled_entries():
        intents.extend(entry.intents)
    intents.extend(["robot_status", "robot_stop", "tasks", "last_task", "help", "unsupported"])
    return list(dict.fromkeys(intents))


def _target_allowlist(app_index: AppIndex) -> list[str]:
    targets = ["workspace"]
    for entry in app_index.enabled_entries():
        targets.extend(entry.allowed_targets)
    return list(dict.fromkeys(targets))


def _has_any(compact: str, raw: str, tokens: list[str]) -> bool:
    lowered = raw.lower()
    return any(token.lower().replace(" ", "") in compact or token.lower() in lowered for token in tokens)


def _multi_angle_request(compact: str, raw: str) -> bool:
    if _has_any(compact, raw, ["多角度", "不同角度", "一组角度", "multiangle", "multi-angle"]):
        return True
    has_lr = _has_any(compact, raw, ["左", "left"]) and _has_any(compact, raw, ["右", "right"])
    has_up = _has_any(compact, raw, ["上", "up"])
    wants_photo = _has_any(compact, raw, ["拍", "照片", "图片", "photo", "picture"])
    return wants_photo and (has_lr or (has_lr and has_up))


def _unsafe_down_request(compact: str, raw: str) -> bool:
    return _has_any(compact, raw, ["向下", "下拍", "下方", "上下", "降低", "pitchdown", "pitch down"])


def _direct_unsafe_request(compact: str, raw: str) -> bool:
    del compact
    lowered = raw.lower()
    patterns = [
        "/" + "cmd_vel",
        "/" + "scan",
        "/" + "odom",
        "/" + "tf",
        "/" + "camera",
        "/" + "servo",
        "move" + "it",
        "nav" + "2",
        "kinematics",
        "jointtrajectory",
        "cartesian",
        "gazebo",
        "gz",
    ]
    return any(pattern.lower() in lowered for pattern in patterns)


def fresh_route_ids() -> tuple[str, str]:
    return new_id("task"), new_id("plan_route")


def _apply_forced_app(plan: dict[str, Any], flags: Any, app_index: AppIndex | None = None) -> dict[str, Any]:
    forced = getattr(flags, "forced_app_id", None)
    if not forced:
        return plan
    if str(plan.get("selected_app_id", "")).startswith("builtin.") and plan.get("selected_app_id") != "unsupported":
        return plan
    entry = app_index.get(str(forced)) if app_index is not None else None
    updated = dict(plan)
    updated["selected_app_id"] = str(forced)
    updated["route_reason"] = f"forced by CLI --app: {forced}"
    app_task_input = dict(updated.get("app_task_input") or {})
    app_task_input.setdefault("text", str(updated.get("user_text") or ""))
    app_task_input["allow_arm_motion"] = bool(getattr(flags, "allow_arm_motion", False))
    app_task_input["assume_yes"] = bool(getattr(flags, "assume_yes", False))
    updated["app_task_input"] = app_task_input
    if entry is not None:
        requires_motion = _forced_requires_motion(entry)
        updated["intent"] = _forced_intent(entry, str(updated.get("intent") or ""))
        updated["requires_robot_motion"] = bool(updated.get("requires_robot_motion")) or requires_motion
        updated["needs_confirmation"] = bool(updated.get("needs_confirmation")) or requires_motion
        updated["risk_class"] = "named_motion" if updated["requires_robot_motion"] else "read_only"
        updated["target"] = "workspace"
        updated["user_summary"] = str(updated.get("user_summary") or f"使用 {entry.app_id} 执行任务")
    return updated


def _normalize_indexed_app_route(plan: dict[str, Any], app_index: AppIndex) -> dict[str, Any]:
    entry = app_index.get(str(plan.get("selected_app_id", "")))
    if entry is None:
        return plan
    updated = dict(plan)
    requires_motion = (
        bool(updated.get("requires_robot_motion"))
        or str(updated.get("risk_class") or "") == "named_motion"
        or entry.risk_classes == ["named_motion"]
    )
    if requires_motion:
        updated["requires_robot_motion"] = True
        updated["needs_confirmation"] = True
        updated["risk_class"] = "named_motion"
    return updated


def _forced_intent(entry: AppIndexEntry, current_intent: str) -> str:
    if current_intent in entry.intents:
        return current_intent
    return entry.intents[0] if entry.intents else current_intent


def _forced_requires_motion(entry: AppIndexEntry) -> bool:
    return "named_motion" in entry.risk_classes
