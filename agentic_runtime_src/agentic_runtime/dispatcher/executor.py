from __future__ import annotations

from typing import Any

from agentic_runtime.types import AppManifest


HELP_TEXT = """AgenticOS natural language gateway

Examples:
  拍一张工作区照片
  从中间、左边、右边、上面拍照并验证差异
  查看最近照片
  最近任务
  上一个任务的结果
  查看状态
  停止机器人
  退出
"""


class DispatcherExecutor:
    def __init__(self, runtime: Any, app_invoker: Any) -> None:
        self.runtime = runtime
        self.app_invoker = app_invoker

    async def execute(self, plan: dict[str, Any], *, parent_session_id: str) -> dict[str, Any]:
        selected_app_id = str(plan["selected_app_id"])
        if selected_app_id == "builtin.help":
            return {"success": True, "type": "help", "message": HELP_TEXT}
        if selected_app_id == "builtin.status":
            return self._status()
        if selected_app_id == "builtin.tasks":
            return self._tasks(limit=int(plan.get("app_task_input", {}).get("limit", 20)))
        if selected_app_id == "builtin.last_task":
            return self._last_task()
        if selected_app_id == "builtin.stop":
            return await self._stop(parent_session_id, reason=str(plan.get("app_task_input", {}).get("reason", "operator_requested")))
        return await self.app_invoker.run_app(
            selected_app_id,
            dict(plan.get("app_task_input") or {}),
            parent_session_id=parent_session_id,
            route_plan_id=str(plan.get("route_plan_id", "")),
        )

    def _status(self) -> dict[str, Any]:
        skills = [skill.name for skill in self.runtime.registry.list_skills()]
        data = self.runtime.monitor.status(skills, ros_bridge=self.runtime.config.ros_bridge_mode)
        data["scheduler"] = self.runtime.scheduler.status()
        data["success"] = True
        return data

    def _tasks(self, limit: int) -> dict[str, Any]:
        records = [record.to_dict() for record in self.runtime.task_log_manager.list_recent(limit=limit)]
        return {"success": True, "type": "tasks", "tasks": records}

    def _last_task(self) -> dict[str, Any]:
        records = self.runtime.task_log_manager.list_recent(limit=2)
        prior = records[1] if len(records) > 1 else (records[0] if records else None)
        if prior is None:
            return {"success": False, "error_code": "TASK_LOG_EMPTY", "reason": "no recent task records"}
        return {"success": True, "type": "last_task", "task": prior.to_dict()}

    async def _stop(self, session_id: str, *, reason: str) -> dict[str, Any]:
        app = AppManifest(
            name="agentic_dispatcher",
            version="0.1.0",
            description="AgenticOS system dispatcher",
            entrypoint="builtin:stop",
            permissions=["robot.stop"],
            required_capabilities=["robot.stop"],
        )
        result = await self.runtime.executor.execute(app, "robot.stop", {"reason": reason}, session_id=session_id)
        return {"success": result.success, "type": "stop", "result": result.to_dict(), "audit_id": result.audit_id}
