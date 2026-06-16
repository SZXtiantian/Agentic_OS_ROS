from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.sdk import AgentContext

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from verifier import verify_photo_differences


async def run(ctx: AgentContext, plan: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    del kwargs
    if not plan or not plan.get("validated"):
        return {
            "schema_version": "1.0",
            "success": False,
            "plan_id": str((plan or {}).get("plan_id", "")),
            "steps": [],
            "error_code": "PHOTO_PLAN_REQUIRED",
            "reason": "main.run only accepts a validated photo plan",
        }
    return await execute_plan(ctx, plan)


async def execute_plan(ctx: AgentContext, plan: dict[str, Any]) -> dict[str, Any]:
    step_results: list[dict[str, Any]] = []
    audit_ids: list[str] = []
    deferred_failure: tuple[str, str] | None = None
    app_storage = _ensure_app_storage(ctx, plan)
    try:
        steps = list(plan["steps"])
        for index, step in enumerate(steps):
            result = await _execute_step(ctx, step, plan=plan, prior_results=step_results, app_storage=app_storage)
            step_results.append(result)
            if result.get("audit_id"):
                audit_ids.append(str(result["audit_id"]))
            for audit_id in result.get("audit_ids", []):
                audit_id_text = str(audit_id)
                if audit_id_text and audit_id_text not in audit_ids:
                    audit_ids.append(audit_id_text)
            if not result.get("success", True):
                error_code = str(result.get("error_code", "STEP_FAILED"))
                reason = str(result.get("reason", ""))
                if deferred_failure is None:
                    deferred_failure = (error_code, reason)
                if _should_continue_for_cleanup(steps, index, result):
                    continue
                return _photo_result(plan, False, step_results, error_code, reason, audit_ids)

        photo_steps = [item for item in step_results if item.get("type") == "capture_photo" and item.get("success")]
        if deferred_failure is not None:
            error_code, reason = deferred_failure
            return _photo_result(plan, False, step_results, error_code, reason, audit_ids)
        if photo_steps:
            await ctx.memory.remember("last_photo", photo_steps[-1])
        await ctx.report.say(plan.get("user_summary", "Robot Photographer task complete."))
        return _photo_result(plan, True, step_results, "", "", audit_ids)
    except AgenticRuntimeError as exc:
        stop_result = None
        if plan.get("requires_motion"):
            try:
                stop_result = (await ctx.robot.stop(reason=f"robot_photographer_error:{exc.code}")).to_dict()
            except AgenticRuntimeError as stop_exc:
                stop_result = {"success": False, "error_code": stop_exc.code, "reason": stop_exc.message}
        failure = _photo_result(plan, False, step_results, exc.code, exc.message, audit_ids)
        if stop_result is not None:
            failure["stop_result"] = stop_result
        return failure


async def _execute_step(
    ctx: AgentContext,
    step: dict[str, Any],
    *,
    plan: dict[str, Any],
    prior_results: list[dict[str, Any]],
    app_storage: dict[str, Path],
) -> dict[str, Any]:
    step_type = step["type"]
    if step_type == "capture_photo":
        photo = await ctx.perception.capture_photo(
            target=str(step.get("target", "workspace")),
            label=str(step.get("label", "photo")),
            timeout_s=int(step.get("timeout_s", 5)),
        )
        projected = _project_photo_to_app_storage(
            photo.to_dict(),
            label=str(step.get("label", "photo")),
            plan=plan,
            ctx=ctx,
            app_storage=app_storage,
        )
        memory_result = await ctx.memory.remember(
            f"photo_capture:{plan.get('plan_id', '')}:{projected.get('label', '')}",
            projected,
        )
        audit_ids = [projected.get("audit_id", ""), getattr(memory_result, "audit_id", "")]
        return {"type": step_type, "success": True, **projected, "audit_ids": [item for item in audit_ids if item]}
    if step_type == "arm_named_action":
        result = await ctx.arm.move_named(str(step["name"]), timeout_s=int(step.get("timeout_s", 8)))
        return {"type": step_type, "success": True, "name": step["name"], "result": result.to_dict(), "audit_id": result.audit_id}
    if step_type == "recent_photos":
        photos = await ctx.storage.list_recent_photos(limit=int(step.get("limit", 5)))
        return {"type": step_type, "success": True, "photos": photos}
    if step_type == "status":
        robot = await ctx.robot.get_state()
        arm = await ctx.arm.get_state()
        photos = await ctx.storage.list_recent_photos(limit=5)
        return {"type": step_type, "success": True, "robot": robot.to_dict(), "arm": arm.to_dict(), "recent_photos": photos}
    if step_type == "stop":
        result = await ctx.robot.stop(reason=str(step.get("reason", "operator_requested_from_robot_photographer")))
        return {"type": step_type, "success": True, "result": result.to_dict(), "audit_id": result.audit_id}
    if step_type == "sleep":
        await asyncio.sleep(float(step.get("duration_s", 0)))
        return {"type": step_type, "success": True, "duration_s": float(step.get("duration_s", 0))}
    if step_type == "verify_photo_differences":
        captures = [item for item in prior_results if item.get("type") == "capture_photo" and item.get("success")]
        verification = verify_photo_differences(
            plan_id=str(plan.get("plan_id", "")),
            capture_results=captures,
            min_difference_score=float(step.get("min_difference_score", 0.08)),
            method=str(step.get("method", "deterministic_cv_metrics")),
            verification_path=app_storage["run_dir"] / "verification.json",
        )
        return {"type": step_type, **verification}
    return {"type": step_type, "success": False, "error_code": "PHOTO_STEP_UNSUPPORTED", "reason": f"unsupported step: {step_type}"}


def _should_continue_for_cleanup(steps: list[dict[str, Any]], index: int, result: dict[str, Any]) -> bool:
    if result.get("type") != "verify_photo_differences":
        return False
    remaining = steps[index + 1 :]
    return any(step.get("type") == "arm_named_action" and step.get("name") == "arm_home" for step in remaining)


def _photo_result(
    plan: dict[str, Any],
    success: bool,
    steps: list[dict[str, Any]],
    error_code: str,
    reason: str,
    audit_ids: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "success": bool(success),
        "plan_id": str(plan.get("plan_id", "")),
        "session_id": str(plan.get("session_id", "")),
        "intent": str(plan.get("intent", "")),
        "risk_class": str(plan.get("risk_class", "")),
        "planner_mode": str(plan.get("planner_mode", "")),
        "user_summary": str(plan.get("user_summary", "")),
        "steps": steps,
        "audit_ids": audit_ids,
        "error_code": error_code,
        "reason": reason,
    }


def _ensure_app_storage(ctx: AgentContext, plan: dict[str, Any]) -> dict[str, Path]:
    session_id = _safe_name(ctx.session_id or "session")
    storage_root = Path(os.environ.get("AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT", str(APP_DIR / "storage"))).expanduser()
    run_dir = storage_root / "runs" / session_id
    paths = {
        "root": storage_root,
        "run_dir": run_dir,
        "run_photos": run_dir / "photos",
        "run_metadata": run_dir / "metadata",
        "run_logs": run_dir / "logs",
        "photos": storage_root / "photos",
        "videos": storage_root / "videos",
        "logs": storage_root / "logs",
        "indexes": storage_root / "indexes",
        "tmp": storage_root / "tmp",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    plan["session_id"] = ctx.session_id
    manifest = {
        "schema_version": "1.0",
        "app_id": ctx.app_manifest.name,
        "session_id": ctx.session_id,
        "plan_id": str(plan.get("plan_id", "")),
        "intent": str(plan.get("intent", "")),
        "storage_role": "app_owned_user_outputs",
        "raw_evidence_role": "runtime_raw_evidence",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return paths


def _project_photo_to_app_storage(
    photo: dict[str, Any],
    *,
    label: str,
    plan: dict[str, Any],
    ctx: AgentContext,
    app_storage: dict[str, Path],
) -> dict[str, Any]:
    raw_image = Path(str(photo.get("image_path", ""))).expanduser()
    raw_metadata = Path(str(photo.get("metadata_path", ""))).expanduser()
    safe_label = _safe_name(label or (photo.get("evidence") or {}).get("label") or "photo")
    capture_index = len(list(app_storage["run_photos"].glob("*.png"))) + 1
    base = f"{capture_index:02d}_{safe_label}"
    app_image = app_storage["run_photos"] / f"{base}.png"
    app_metadata = app_storage["run_metadata"] / f"{base}.json"

    if not raw_image.exists():
        return {
            **photo,
            "label": safe_label,
            "success": False,
            "error_code": "PHOTO_RAW_EVIDENCE_IMAGE_MISSING",
            "reason": f"raw evidence image is missing: {raw_image}",
            "raw_evidence_image_path": str(raw_image),
            "raw_evidence_metadata_path": str(raw_metadata),
            "app_image_path": str(app_image),
            "app_metadata_path": str(app_metadata),
        }
    _copy_file(raw_image, app_image)
    raw_metadata_data = _read_json_file(raw_metadata)
    metadata = {
        **raw_metadata_data,
        "schema_version": "1.0",
        "app_id": ctx.app_manifest.name,
        "session_id": ctx.session_id,
        "plan_id": str(plan.get("plan_id", "")),
        "label": safe_label,
        "raw_evidence_image_path": str(raw_image),
        "raw_evidence_metadata_path": str(raw_metadata),
        "app_image_path": str(app_image),
        "app_metadata_path": str(app_metadata),
        "app_storage_root": str(app_storage["root"]),
        "app_run_dir": str(app_storage["run_dir"]),
    }
    app_metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    app_photo = app_storage["photos"] / app_image.name
    _copy_file(app_image, app_photo)
    index_entry = {
        "kind": "photo",
        "app_id": ctx.app_manifest.name,
        "session_id": ctx.session_id,
        "plan_id": str(plan.get("plan_id", "")),
        "label": safe_label,
        "image_path": str(app_image),
        "metadata_path": str(app_metadata),
        "app_image_path": str(app_image),
        "app_metadata_path": str(app_metadata),
        "raw_evidence_image_path": str(raw_image),
        "raw_evidence_metadata_path": str(raw_metadata),
        "audit_id": str(photo.get("audit_id", "")),
    }
    _append_jsonl(app_storage["indexes"] / "photos.jsonl", index_entry)
    enriched_evidence = dict(photo.get("evidence") or {})
    enriched_evidence.update(index_entry)
    return {
        **photo,
        "label": safe_label,
        "image_path": str(app_image),
        "metadata_path": str(app_metadata),
        "raw_evidence_image_path": str(raw_image),
        "raw_evidence_metadata_path": str(raw_metadata),
        "app_image_path": str(app_image),
        "app_metadata_path": str(app_metadata),
        "app_storage_root": str(app_storage["root"]),
        "app_run_dir": str(app_storage["run_dir"]),
        "evidence": enriched_evidence,
    }


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _safe_name(value: Any) -> str:
    text = str(value or "")
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    return safe.strip("._") or "photo"
