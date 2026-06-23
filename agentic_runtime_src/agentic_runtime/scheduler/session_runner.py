from __future__ import annotations

from typing import Any

from agentic_runtime.app_result import APP_RESULT_INVALID, validate_app_result_payload
from agentic_runtime.app_factory import AppFactory
from agentic_runtime.context_manager import ContextManager
from agentic_runtime.real_only import unsupported_task_field
from agentic_runtime.session import SessionManager
from agentic_runtime.storage import StorageManager


class SessionRunner:
    def __init__(
        self,
        app_factory: AppFactory,
        session_manager: SessionManager,
        storage_manager: StorageManager,
        context_manager: ContextManager,
    ) -> None:
        self.app_factory = app_factory
        self.session_manager = session_manager
        self.storage_manager = storage_manager
        self.context_manager = context_manager

    async def run_app(self, app_id: str, place: str = "厨房", **kwargs: Any) -> dict[str, Any]:
        task = dict(kwargs)
        unsupported = unsupported_task_field(task)
        if unsupported is not None:
            return {"session_id": "", "app_id": app_id, "status": "failed", "result": unsupported}
        task.setdefault("place", place)
        session = self.session_manager.create_session(app_id, task=task)
        self.context_manager.snapshot(session.session_id, app_id, task=task)
        self.session_manager.start_session(session.session_id)
        try:
            app_result = await self.app_factory.run_app(app_id, session_id=session.session_id, **task)
            if not isinstance(app_result, dict):
                result, _ = validate_app_result_payload(app_result, source=f"{app_id}:app_factory")
            else:
                result, _ = validate_app_result_payload(app_result.get("result"), source=f"{app_id}:result")
            if result.get("success"):
                self.storage_manager.write_artifact(
                    session.session_id,
                    "inspection_report.json",
                    result,
                    artifact_type="inspection_report",
                )
                record = self.session_manager.complete_session(session.session_id, result)
            else:
                record = self.session_manager.fail_session(session.session_id, str(result.get("error_code") or APP_RESULT_INVALID), result)
            self.context_manager.snapshot(
                session.session_id,
                app_id,
                task=task,
                error_code=record.error_code,
                cancel_requested=record.stop_requested,
            )
            return {"session_id": session.session_id, "app_id": app_id, "status": record.status, "result": result}
        except Exception as exc:
            record = self.session_manager.fail_session(session.session_id, "APP_EXCEPTION", {"success": False, "reason": str(exc)})
            self.context_manager.snapshot(session.session_id, app_id, task=task, error_code=record.error_code)
            return {"session_id": session.session_id, "app_id": app_id, "status": record.status, "result": record.result}
