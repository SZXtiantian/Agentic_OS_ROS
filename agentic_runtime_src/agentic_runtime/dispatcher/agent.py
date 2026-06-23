from __future__ import annotations

from typing import Any

from .app_index import AppIndex
from .errors import DispatchError
from .executor import DispatcherExecutor
from .planner import DispatcherPlanner
from .validation import DispatcherValidator


class DispatcherAgent:
    def __init__(
        self,
        runtime: Any,
        *,
        app_index: AppIndex | None = None,
        planner: DispatcherPlanner | None = None,
        validator: DispatcherValidator | None = None,
        executor: DispatcherExecutor | None = None,
    ) -> None:
        self.runtime = runtime
        self.app_index = app_index or AppIndex.load(runtime.config.app_root)
        self.planner = planner or DispatcherPlanner(llm_chat=getattr(runtime, "llm_chat", None))
        self.validator = validator or DispatcherValidator()
        self.executor = executor

    async def arun(self, user_text: str, flags: Any) -> dict[str, Any]:
        task_log = self.runtime.task_log_manager
        task_id = task_log.new_task_id()
        route_plan_id = task_log.new_route_plan_id()
        dispatcher_session = self.runtime.session_manager.create_session(
            "agentic_dispatcher",
            task={"user_text": user_text, "route_plan_id": route_plan_id},
        )
        self.runtime.session_manager.start_session(dispatcher_session.session_id)

        route_plan: dict[str, Any] = {}
        try:
            route_plan = self.planner.plan(user_text, self.app_index, flags, task_id=task_id, route_plan_id=route_plan_id)
            plan_path = task_log.write_route_plan(route_plan)
            task_log.create_task(user_text, route_plan, dispatcher_session.session_id)
            validated = self.validator.validate(route_plan, self.app_index, flags)
            if bool(getattr(flags, "show_plan", False)) or bool(getattr(flags, "dry_run", False)):
                summary = _summary_from_result(
                    {
                        "success": True,
                        "status": "dry_run" if bool(getattr(flags, "dry_run", False)) else "planned",
                        "summary": validated.get("user_summary", ""),
                    }
                )
                status = "dry_run" if bool(getattr(flags, "dry_run", False)) else "completed"
                summary["status"] = status
                record = task_log.complete_task(task_id, summary, {"route_plan_path": str(plan_path)})
                self.runtime.session_manager.complete_session(dispatcher_session.session_id, {"success": True, "route_plan": validated})
                return _dispatch_result(True, status, validated, dispatcher_session.session_id, [], {}, summary, str(task_log.path), record)

            selected_agents = _selected_agents(validated)
            if selected_agents:
                task_log.mark_running(task_id, selected_agents)
            executor = self.executor or _build_executor(self.runtime, self.app_index)
            raw_app_result = await executor.execute(validated, parent_session_id=dispatcher_session.session_id)
            app_result = _coerce_app_result(raw_app_result)
            child_session_id = str(app_result.get("session_id", ""))
            if child_session_id and selected_agents:
                task_log.attach_agent_session(task_id, str(validated["selected_app_id"]), child_session_id)
                for item in selected_agents:
                    if item.get("agent_id") == validated["selected_app_id"]:
                        item["session_id"] = child_session_id
                        item["status"] = "running"
            success_check = _result_success_check(app_result)
            success = bool(success_check["success"])
            summary = _summary_from_result(app_result, success_override=success)
            detail_refs = _detail_refs(app_result, plan_path, self.runtime)
            if not success_check["valid"]:
                error_code = str(success_check["error_code"])
                reason = str(success_check["reason"])
                summary["error_code"] = error_code
                summary["summary"] = reason
                record = task_log.fail_task(task_id, error_code, reason, detail_refs)
                self.runtime.session_manager.fail_session(dispatcher_session.session_id, error_code, {"success": False, "app_result": app_result})
                return _dispatch_result(False, "failed", validated, dispatcher_session.session_id, selected_agents, app_result, summary, str(task_log.path), record, error_code, reason)
            if success:
                record = task_log.complete_task(task_id, summary, detail_refs)
                self.runtime.session_manager.complete_session(dispatcher_session.session_id, {"success": True, "app_result": app_result})
                return _dispatch_result(True, "completed", validated, dispatcher_session.session_id, selected_agents, app_result, summary, str(task_log.path), record)
            error_code = str(summary.get("error_code") or app_result.get("error_code") or "DISPATCH_APP_FAILED")
            reason = str(summary.get("summary") or app_result.get("reason") or "selected app failed")
            record = task_log.fail_task(task_id, error_code, reason, detail_refs)
            self.runtime.session_manager.fail_session(dispatcher_session.session_id, error_code, {"success": False, "app_result": app_result})
            return _dispatch_result(False, "failed", validated, dispatcher_session.session_id, selected_agents, app_result, summary, str(task_log.path), record, error_code, reason)
        except DispatchError as exc:
            if route_plan:
                try:
                    task_log.reject_task(task_id, exc.code, exc.reason, route_plan)
                except KeyError:
                    pass
            self.runtime.session_manager.fail_session(dispatcher_session.session_id, exc.code, {"success": False, "reason": exc.reason})
            return {
                "success": False,
                "status": "rejected",
                "error_code": exc.code,
                "message": exc.reason,
                "task_id": task_id,
                "route_plan_id": route_plan_id,
                "dispatcher_session_id": dispatcher_session.session_id,
                "selected_app_id": str(route_plan.get("selected_app_id", "unsupported")) if route_plan else "unsupported",
                "route_plan": route_plan,
                "task_log_path": str(task_log.path),
            }
        except Exception as exc:
            error_code = "DISPATCH_UNEXPECTED_ERROR"
            reason = str(exc)
            if route_plan:
                try:
                    task_log.fail_task(task_id, error_code, reason)
                except KeyError:
                    pass
            self.runtime.session_manager.fail_session(dispatcher_session.session_id, error_code, {"success": False, "reason": reason})
            return {
                "success": False,
                "status": "failed",
                "error_code": error_code,
                "message": reason,
                "task_id": task_id,
                "route_plan_id": route_plan_id,
                "dispatcher_session_id": dispatcher_session.session_id,
                "selected_app_id": str(route_plan.get("selected_app_id", "unsupported")) if route_plan else "unsupported",
                "route_plan": route_plan,
                "task_log_path": str(task_log.path),
            }


def _build_executor(runtime: Any, app_index: AppIndex) -> DispatcherExecutor:
    from agentic_runtime.app_invoker import AppInvoker

    return DispatcherExecutor(runtime, AppInvoker(runtime, app_index))


def _selected_agents(plan: dict[str, Any]) -> list[dict[str, Any]]:
    app_id = str(plan.get("selected_app_id", ""))
    if app_id.startswith("builtin.") or app_id == "unsupported":
        return []
    return [{"agent_id": app_id, "role": "primary_executor", "reason": str(plan.get("route_reason", "")), "session_id": "", "status": "planned"}]


def _coerce_app_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    return {
        "success": False,
        "error_code": "DISPATCH_APP_RESULT_INVALID",
        "reason": f"dispatcher executor returned {type(result).__name__}",
    }


def _result_success_check(result: dict[str, Any]) -> dict[str, Any]:
    app_result = result.get("result")
    if "result" in result:
        if not isinstance(app_result, dict):
            return _invalid_result_success("result must be an object")
        if "success" in app_result:
            return _success_field(app_result["success"], "result.success")
        return _invalid_result_success("result.success field is required")
    if "success" in result:
        return _success_field(result["success"], "success")
    return _invalid_result_success("success field is required")


def _success_field(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, bool):
        return _invalid_result_success(f"{field_name} field must be boolean")
    return {"valid": True, "success": value, "error_code": "", "reason": ""}


def _invalid_result_success(reason: str) -> dict[str, Any]:
    return {
        "valid": False,
        "success": False,
        "error_code": "DISPATCH_APP_RESULT_INVALID",
        "reason": reason,
    }


def _summary_from_result(result: dict[str, Any], *, success_override: bool | None = None) -> dict[str, Any]:
    raw_app_result = result.get("result") if isinstance(result.get("result"), dict) else result
    app_result = dict(raw_app_result)
    steps = list(app_result.get("steps") or [])
    app_paths: list[str] = []
    raw_paths: list[str] = []
    audit_ids: list[str] = []
    for step in steps:
        for key in ("app_image_path", "app_metadata_path", "verification_path"):
            if step.get(key):
                app_paths.append(str(step[key]))
        for key in ("raw_evidence_image_path", "raw_evidence_metadata_path"):
            if step.get(key):
                raw_paths.append(str(step[key]))
        if step.get("audit_id"):
            audit_ids.append(str(step["audit_id"]))
        for audit_id in step.get("audit_ids", []):
            if audit_id:
                audit_ids.append(str(audit_id))
    audit_ids.extend(str(item) for item in app_result.get("audit_ids", []) if item)
    summary = str(app_result.get("user_summary") or app_result.get("summary") or result.get("summary") or "")
    if not summary and result.get("type"):
        summary = str(result.get("type"))
    if success_override is None:
        success_override = bool(_result_success_check(result)["success"])
    return {
        "success": bool(success_override),
        "error_code": str(app_result.get("error_code") or result.get("error_code") or ""),
        "summary": summary,
        "app_output_paths": list(dict.fromkeys(app_paths)),
        "raw_evidence_paths": list(dict.fromkeys(raw_paths)),
        "audit_ids": list(dict.fromkeys(audit_ids)),
    }


def _detail_refs(result: dict[str, Any], plan_path, runtime: Any) -> dict[str, Any]:
    refs = {
        "route_plan_path": str(plan_path),
        "audit_log_path": str(runtime.config.audit_log_path),
    }
    if result.get("session_id"):
        refs["app_session_paths"] = [str(runtime.session_manager.store.session_dir(str(result["session_id"])))]
    raw_app_result = result.get("result") if isinstance(result.get("result"), dict) else result
    app_result = dict(raw_app_result)
    run_dirs = []
    for step in app_result.get("steps", []):
        if step.get("app_run_dir"):
            run_dirs.append(str(step["app_run_dir"]))
    if run_dirs:
        refs["app_storage_paths"] = list(dict.fromkeys(run_dirs))
    return refs


def _dispatch_result(
    success: bool,
    status: str,
    plan: dict[str, Any],
    dispatcher_session_id: str,
    selected_agents: list[dict[str, Any]],
    app_result: dict[str, Any],
    summary: dict[str, Any],
    task_log_path: str,
    record: Any,
    error_code: str = "",
    message: str = "",
) -> dict[str, Any]:
    return {
        "success": bool(success),
        "status": status,
        "task_id": str(plan.get("task_id", "")),
        "route_plan_id": str(plan.get("route_plan_id", "")),
        "dispatcher_session_id": dispatcher_session_id,
        "selected_app_id": str(plan.get("selected_app_id", "")),
        "selected_agents": record.to_dict().get("selected_agents", selected_agents) if hasattr(record, "to_dict") else selected_agents,
        "risk_class": str(plan.get("risk_class", "")),
        "requires_robot_motion": bool(plan.get("requires_robot_motion", False)),
        "needs_confirmation": bool(plan.get("needs_confirmation", False)),
        "route_plan": plan,
        "app_result": app_result,
        "result_summary": summary,
        "task_log_path": task_log_path,
        "task_record": record.to_dict() if hasattr(record, "to_dict") else {},
        "error_code": error_code,
        "message": message,
    }
