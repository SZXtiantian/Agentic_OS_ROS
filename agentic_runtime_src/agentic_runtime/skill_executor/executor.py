from __future__ import annotations

import time
from typing import Any

from agentic_runtime.audit import AuditLogger
from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_runtime.errors import (
    AgenticRuntimeError,
    PermissionDeniedError,
    ResourceLockedError,
    SafetyRejectedError,
    SchemaInvalidError,
    SkillTimeoutError,
)
from agentic_runtime.permission_manager import PermissionManager
from agentic_runtime.skill_registry import SkillRegistry
from agentic_runtime.skill_registry.schema_validator import validate_input
from agentic_runtime.syscall import SkillSyscall, SyscallStatus
from agentic_runtime.types import AppManifest, SkillCall, SkillResult

from .cancellation import CancellationManager
from .dispatcher import SkillDispatcher
from .resource_manager import ResourceManager
from .timeout import run_with_timeout


class SkillExecutor:
    def __init__(
        self,
        registry: SkillRegistry,
        permission_manager: PermissionManager,
        resource_manager: ResourceManager,
        dispatcher: SkillDispatcher,
        audit_logger: AuditLogger,
        cancellation_manager: CancellationManager | None = None,
        syscall_store=None,
        session_manager=None,
        access_manager: AccessManager | None = None,
        event_sink=None,
    ) -> None:
        self.registry = registry
        self.permission_manager = permission_manager
        self.resource_manager = resource_manager
        self.dispatcher = dispatcher
        self.audit_logger = audit_logger
        self.cancellation_manager = cancellation_manager or CancellationManager()
        self.syscall_store = syscall_store
        self.session_manager = session_manager
        self.access_manager = access_manager
        self.event_sink = event_sink

    async def execute(
        self,
        app: AppManifest,
        skill_name: str,
        args: dict[str, Any] | None = None,
        session_id: str = "default",
    ) -> SkillResult:
        args = dict(args or {})
        skill = self.registry.get_skill(skill_name)
        call = SkillCall(skill.name, args, app.name, session_id)
        syscall = SkillSyscall.create(app.name, session_id, skill.name, args)
        self._record_syscall(syscall)
        self._set_current_skill(session_id, skill.name)
        started = time.monotonic()
        permission_result = "not_checked"
        safety_result = "not_required"
        resource_result = "not_required"
        acquired: list[str] = []
        backend_name = str(skill.backend.get("type", "mock"))

        try:
            validate_input(skill.input_schema, args)
            self.permission_manager.check(app, skill)
            permission_result = "allowed"
            syscall.permission_result = permission_result

            if self.access_manager is not None and self._requires_access_check(skill.name):
                access_decision = self.access_manager.check(
                    AccessRequest(
                        subject=AccessSubject(app_id=app.name, agent_name=app.name, permissions=tuple(app.permissions)),
                        action="execute",
                        resource=AccessResource(self._access_resource_type(skill.name), skill.name),
                    )
                )
                if not access_decision.allowed:
                    raise PermissionDeniedError(access_decision.reason or access_decision.error_code)

            if skill.name == "robot.stop":
                self.cancellation_manager.cancel_session(session_id)

            if self._requires_safety(skill.safety_constraints):
                safety_response = await self.dispatcher.bridge_client.check_safety(skill.name, args, app.name)
                self._emit_event(
                    "robot.safety_checked",
                    app_id=app.name,
                    session_id=session_id,
                    skill_name=skill.name,
                    allowed=bool(safety_response.get("allowed", False)),
                    error_code=str(safety_response.get("error_code", "")),
                )
                if not safety_response.get("allowed", False):
                    raise SafetyRejectedError(
                        safety_response.get("error_code", "SAFETY_REJECTED"),
                        safety_response.get("reason", "safety rejected"),
                    )
                safety_result = "allowed"
                syscall.safety_result = safety_result

            for resource in skill.resource_requirements.get("locks", []):
                self.resource_manager.acquire(str(resource), session_id, call.call_id)
                acquired.append(str(resource))
            if acquired:
                resource_result = "locked"
                syscall.resource_lock_result = resource_result

            operation_timeout_s = int(args.get("timeout_s") or skill.timeout_s)
            timeout_s = operation_timeout_s + int(skill.safety_constraints.get("runtime_timeout_margin_s", 0))
            cancel_event = self.cancellation_manager.event_for(session_id)
            syscall.mark_started(SyscallStatus.EXECUTING)
            self._record_syscall(syscall)
            raw = await run_with_timeout(
                self.dispatcher.dispatch(skill.name, args, app.name, session_id, cancel_event=cancel_event),
                timeout_s,
            )
            result = self._result_from_backend(raw)
            status = "succeeded" if result.success else self._status_for_error(result.error_code)
            audit_id = self._audit(
                call,
                permission_result,
                safety_result,
                resource_result,
                backend_name,
                status,
                result.error_code,
                started,
                result.to_dict(),
            )
            result.audit_id = audit_id
            syscall.permission_result = permission_result
            syscall.safety_result = safety_result
            syscall.resource_lock_result = resource_result
            syscall.finish(
                self._syscall_status(status),
                result=result.to_dict(),
                error_code=result.error_code,
                audit_id=audit_id,
            )
            self._record_syscall(syscall)
            return result

        except (PermissionDeniedError, SafetyRejectedError, ResourceLockedError, SchemaInvalidError, SkillTimeoutError) as exc:
            if isinstance(exc, PermissionDeniedError):
                permission_result = "denied"
            elif isinstance(exc, SafetyRejectedError):
                safety_result = "denied"
            elif isinstance(exc, ResourceLockedError):
                resource_result = "denied"
            status = "timeout" if isinstance(exc, SkillTimeoutError) else "rejected"
            result = SkillResult(
                success=False,
                error_code=exc.code,
                reason=exc.message,
                recoverable=exc.recoverable,
                suggested_recovery=list(exc.suggested_recovery),
            )
            result.audit_id = self._audit(
                call,
                permission_result,
                safety_result,
                resource_result,
                backend_name,
                status,
                result.error_code,
                started,
                result.to_dict(),
            )
            syscall.permission_result = permission_result
            syscall.safety_result = safety_result
            syscall.resource_lock_result = resource_result
            syscall.finish(
                self._syscall_status(status),
                result=result.to_dict(),
                error_code=result.error_code,
                audit_id=result.audit_id,
            )
            self._record_syscall(syscall)
            return result
        except Exception as exc:
            result = SkillResult(
                success=False,
                error_code="UNEXPECTED_ERROR",
                reason=str(exc),
                recoverable=True,
                suggested_recovery=["retry", "ask_human", "cancel"],
            )
            result.audit_id = self._audit(
                call,
                permission_result,
                safety_result,
                resource_result,
                backend_name,
                "failed",
                result.error_code,
                started,
                result.to_dict(),
            )
            syscall.permission_result = permission_result
            syscall.safety_result = safety_result
            syscall.resource_lock_result = resource_result
            syscall.finish(
                SyscallStatus.FAILED,
                result=result.to_dict(),
                error_code=result.error_code,
                audit_id=result.audit_id,
            )
            self._record_syscall(syscall)
            return result
        finally:
            for resource in acquired:
                self.resource_manager.release(resource, session_id, call.call_id)

    def _requires_safety(self, constraints: dict[str, Any]) -> bool:
        return bool(
            constraints.get("require_known_place")
            or constraints.get("require_localized")
            or constraints.get("require_estop_released")
            or constraints.get("forbidden_zone_check")
            or constraints.get("camera_target_allowlist")
            or constraints.get("named_action_allowlist")
            or constraints.get("workspace_bounds_check")
            or constraints.get("gripper_allowlist")
        )

    def _requires_access_check(self, skill_name: str) -> bool:
        return skill_name in {
            "robot.navigate_to",
            "robot.stop",
            "robot.inspect_area",
            "arm.move_named",
            "gripper.set",
            "perception.observe",
            "perception.capture_photo",
        }

    def _access_resource_type(self, skill_name: str) -> str:
        if skill_name in {"robot.inspect_area", "perception.observe", "perception.capture_photo"}:
            return "robot_sensor"
        return "robot_motion"

    def _result_from_backend(self, raw: dict[str, Any]) -> SkillResult:
        success = bool(raw.get("success", raw.get("answered", True)))
        if success:
            data = dict(raw)
            data.pop("success", None)
            return SkillResult(success=True, data=data)
        return SkillResult(
            success=False,
            data=dict(raw),
            error_code=str(raw.get("error_code", "UNEXPECTED_ERROR")),
            reason=str(raw.get("reason", raw.get("message", "skill failed"))),
            recoverable=True,
            suggested_recovery=["retry", "ask_human", "cancel"],
        )

    def _status_for_error(self, error_code: str) -> str:
        if error_code == "SKILL_CANCELLED":
            return "cancelled"
        if error_code in {"SKILL_TIMEOUT", "NAVIGATION_TIMEOUT"}:
            return "timeout"
        return "failed"

    def _syscall_status(self, skill_status: str) -> str:
        if skill_status == "succeeded":
            return SyscallStatus.DONE
        if skill_status == "timeout":
            return SyscallStatus.TIMEOUT
        if skill_status == "cancelled":
            return SyscallStatus.CANCELLED
        if skill_status == "rejected":
            return SyscallStatus.REJECTED
        return SyscallStatus.FAILED

    def _record_syscall(self, syscall: SkillSyscall) -> None:
        if self.syscall_store is not None:
            self.syscall_store.append(syscall.session_id, syscall.to_dict())

    def _set_current_skill(self, session_id: str, skill_name: str) -> None:
        if self.session_manager is not None:
            self.session_manager.set_current_skill(session_id, skill_name)

    def _audit(
        self,
        call: SkillCall,
        permission_result: str,
        safety_result: str,
        resource_result: str,
        backend: str,
        status: str,
        error_code: str,
        started: float,
        result: dict[str, Any] | None = None,
    ) -> str:
        return self.audit_logger.write(
            {
                "app_id": call.app_id,
                "session_id": call.session_id,
                "skill_name": call.skill_name,
                "args": call.args,
                "permission_result": permission_result,
                "safety_result": safety_result,
                "resource_lock_result": resource_result,
                "backend": backend,
                "status": status,
                "error_code": error_code,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "result": result or {},
            }
        )

    def _emit_event(self, event_type: str, **metadata: Any) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(event_type, **metadata)


def raise_for_result(result: SkillResult) -> None:
    if result.success:
        return
    code = result.error_code
    message = result.reason
    if code == "PERMISSION_DENIED":
        raise PermissionDeniedError(message)
    if code in {"FORBIDDEN_ZONE", "ESTOP_PRESSED", "ROBOT_NOT_LOCALIZED", "SAFETY_REJECTED"}:
        raise SafetyRejectedError(code, message)
    if code in {"SKILL_TIMEOUT", "NAVIGATION_TIMEOUT"}:
        raise SkillTimeoutError(message)
    if code == "RESOURCE_LOCKED":
        raise ResourceLockedError(message)
    if code == "SCHEMA_INVALID":
        raise SchemaInvalidError(message)
    raise AgenticRuntimeError(code or "UNEXPECTED_ERROR", message or "skill failed")
