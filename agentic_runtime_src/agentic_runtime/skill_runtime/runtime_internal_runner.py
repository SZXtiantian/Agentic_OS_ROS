from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agentic_runtime.config import find_repo_root
from agentic_runtime.types import SkillManifest

from .context import SkillRuntimeContext


class RuntimeInternalSkillRunner:
    async def run(self, skill: SkillManifest, args: dict[str, Any], context: SkillRuntimeContext) -> dict[str, Any]:
        operation = str(skill.implementation.get("operation") or "")
        if operation == "memory.remember":
            return _memory_remember(context, args)
        if operation == "memory.recall":
            return _memory_recall(context, args)
        if operation == "storage.list_recent_photos":
            return _list_recent_photos(int(args.get("limit", 5)), app_id=context.app_id)
        if operation == "human.ask":
            return await _ask_human(context, args)
        if operation == "report.say":
            return await context.bridge_client.report_say(args["message"])
        return {
            "success": False,
            "error_code": "SKILL_BACKEND_UNAVAILABLE",
            "reason": f"runtime_internal operation is not configured: {operation}",
        }


def _memory_remember(context: SkillRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    result = context.memory_store.remember(context.app_id, context.session_id, args["key"], args.get("value"))
    if isinstance(result, dict):
        if "success" not in result or not isinstance(result.get("success"), bool):
            return {
                "success": False,
                "error_code": "MEMORY_RESULT_INVALID",
                "reason": "memory remember result missing boolean success field",
                "raw_type": type(result).__name__,
            }
        return result if not result.get("success", False) else {"success": True, **result}
    return {
        "success": False,
        "error_code": "MEMORY_RESULT_INVALID",
        "reason": f"memory remember backend returned {type(result).__name__}",
    }


def _memory_recall(context: SkillRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    if hasattr(context.memory_store, "recall_result"):
        result = context.memory_store.recall_result(context.app_id, args["key"])
        if isinstance(result, dict):
            if "success" not in result or not isinstance(result.get("success"), bool):
                return {
                    "success": False,
                    "error_code": "MEMORY_RESULT_INVALID",
                    "reason": "memory recall result missing boolean success field",
                    "raw_type": type(result).__name__,
                }
            return result
        return {
            "success": False,
            "error_code": "MEMORY_RESULT_INVALID",
            "reason": f"memory recall backend returned {type(result).__name__}",
        }
    return {
        "success": False,
        "error_code": "MEMORY_BACKEND_UNAVAILABLE",
        "reason": "memory backend does not implement recall_result contract",
    }


async def _ask_human(context: SkillRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    if context.human_channel is None:
        return {"success": False, "answered": False, "answer": "", "error_code": "HUMAN_BACKEND_UNAVAILABLE"}
    return await context.human_channel.ask(
        question=args["question"],
        options=list(args.get("options") or []),
        timeout_s=int(args.get("timeout_s", 60)),
        require_confirmation=bool(args.get("require_confirmation", False)),
        app_id=context.app_id,
        session_id=context.session_id,
        correlation_id=str(args.get("correlation_id") or ""),
        cancel_event=context.cancel_event,
    )


def _list_recent_photos(limit: int, app_id: str = "") -> dict[str, Any]:
    app_index = _app_photo_index(app_id)
    if app_index is not None and app_index.exists():
        app_result = _read_photo_index(app_index, limit)
        if app_result.get("success") and app_result.get("photos"):
            app_result["source"] = "app_storage"
            return app_result
    photos_root = Path(os.environ.get("AGENTIC_PHOTO_EVIDENCE_ROOT", "/opt/agentic/var/evidence/photos"))
    index_path = photos_root / "index.jsonl"
    raw_result = _read_photo_index(index_path, limit)
    raw_result["source"] = "runtime_raw_evidence"
    return raw_result


def _app_photo_index(app_id: str) -> Path | None:
    if app_id != "robot_photographer_agent":
        return None
    app_root = Path(os.environ.get("AGENTIC_APP_ROOT", find_repo_root().parent / "agentic_apps")).expanduser()
    storage_root = Path(
        os.environ.get(
            "AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT",
            str(app_root / "robot_photographer_agent" / "storage"),
        )
    ).expanduser()
    return storage_root / "indexes" / "photos.jsonl"


def _read_photo_index(index_path: Path, limit: int) -> dict[str, Any]:
    if not index_path.exists():
        return {"success": True, "photos": [], "index_path": str(index_path)}
    entries: list[dict[str, Any]] = []
    try:
        for line in index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                entries.append(parsed)
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "error_code": "PHOTO_INDEX_CORRUPT", "reason": str(exc), "index_path": str(index_path)}
    return {"success": True, "photos": entries[-max(limit, 0) :], "index_path": str(index_path)}
