from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.capability import RobotCapabilityManager
from agentic_os.kernel.hooks import KernelQueueStore
from agentic_os.kernel.human import HumanInteractionManager
from agentic_os.kernel.llm_core import LLMAdapter, LLMConfig
from agentic_os.kernel.memory import MemoryManager
from agentic_os.kernel.scheduler import FIFOKernelScheduler
from agentic_os.kernel.storage import StorageManager
from agentic_os.kernel.system_call import KernelQuery, SyscallExecutionResult, SyscallExecutor
from agentic_os.kernel.tool import ToolManager


class KernelService:
    def __init__(self, runtime_server=None, config=None, audit_logger=None, managers: dict[str, Any] | None = None) -> None:
        self.runtime_server = runtime_server
        self.config = config or getattr(runtime_server, "config", None)
        self.audit_logger = audit_logger or getattr(runtime_server, "audit_logger", None)
        self.access_manager = AccessManager()
        self.queue_store = KernelQueueStore()
        self.llm = LLMAdapter([LLMConfig(name="mock-kernel", backend="mock")])
        self.memory = MemoryManager(access_manager=self.access_manager)
        self.storage = StorageManager(self._storage_root(), access_manager=self.access_manager)
        self.tool = ToolManager()
        self.robot_motion = RobotCapabilityManager()
        self.robot_sensor = RobotCapabilityManager()
        self.human = HumanInteractionManager()
        self.managers = {
            "llm": self.llm,
            "memory": self.memory,
            "storage": self.storage,
            "tool": self.tool,
            "robot_motion": self.robot_motion,
            "robot_sensor": self.robot_sensor,
            "human": self.human,
            **dict(managers or {}),
        }
        self.scheduler = FIFOKernelScheduler(self.queue_store, self.managers)
        self.executor = SyscallExecutor(queue_store=self.queue_store)
        self._recent_syscalls: list[dict[str, Any]] = []
        self._recent_lock = Lock()

    def start(self) -> None:
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.stop()

    def execute_request(
        self,
        agent_name: str,
        query: KernelQuery,
        timeout_s: float | None = None,
    ) -> SyscallExecutionResult:
        started = time.monotonic()
        result = self.executor.execute_request(agent_name, query, timeout_s=timeout_s)
        self._record_kernel_syscall(agent_name, query, result, started)
        return result

    def status(self) -> dict[str, Any]:
        status = self.kernel_status()
        if self.runtime_server is None:
            return status
        skills = [skill.name for skill in self.runtime_server.registry.list_skills()]
        status["runtime"] = self.runtime_server.monitor.status(skills, ros_bridge=self.runtime_server.config.ros_bridge_mode)
        return status

    def kernel_status(self) -> dict[str, Any]:
        return {
            "scheduler": self.scheduler.status(),
            "queues": self.queue_store.snapshot(),
            "managers": {name: "ready" for name in sorted(self.managers)},
            "access": {"policy": self.access_manager.policy.__class__.__name__},
            "audit": {"enabled": self.audit_logger is not None},
            "recent_syscalls": self.recent_syscalls(),
        }

    def core_status(self) -> dict[str, Any]:
        status = {"kernel": self.kernel_status()}
        if self.runtime_server is not None:
            status.update(
                {
                    "runtime_scheduler": self.runtime_server.scheduler.status(),
                    "sessions": len(self.runtime_server.session_manager.list_sessions(limit=100)),
                    "bridge": self.runtime_server.bridge_manager.status(),
                }
            )
        return status

    async def run_app(self, app_id: str, place: str = "厨房", mock: bool = True) -> dict[str, Any]:
        if self.runtime_server is None:
            return {"success": False, "error_code": "RUNTIME_SERVER_NOT_WIRED"}
        return await self.runtime_server.scheduler.run_app(app_id, place=place, mock=mock)

    def _storage_root(self) -> Path:
        if self.config is not None:
            return Path(getattr(self.config, "storage_root"))
        return Path("/tmp/agentic_kernel_storage")

    def recent_syscalls(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._recent_lock:
            return list(self._recent_syscalls[-limit:])

    def _record_kernel_syscall(
        self,
        agent_name: str,
        query: KernelQuery,
        result: SyscallExecutionResult,
        started_monotonic: float,
    ) -> None:
        duration_ms = result.duration_ms or int((time.monotonic() - started_monotonic) * 1000)
        queue_name = str(result.metadata.get("queue_name", getattr(result.syscall, "target", "")))
        status = "succeeded" if result.success else "failed"
        record = {
            "agent_name": agent_name,
            "operation_type": query.operation_type,
            "queue_name": queue_name,
            "pid": result.metadata.get("pid"),
            "success": result.success,
            "status": status,
            "error_code": result.error_code,
            "duration_ms": duration_ms,
        }
        if self.audit_logger is not None:
            audit_id = self.audit_logger.write(
                {
                    "app_id": agent_name,
                    "session_id": str(query.metadata.get("session_id", "kernel")),
                    "skill_name": f"kernel.{queue_name}.{query.operation_type}",
                    "args": dict(query.params),
                    "permission_result": "kernel_checked",
                    "safety_result": "not_required",
                    "resource_lock_result": "not_required",
                    "backend": queue_name,
                    "status": status,
                    "error_code": result.error_code,
                    "duration_ms": duration_ms,
                }
            )
            record["audit_id"] = audit_id
        with self._recent_lock:
            self._recent_syscalls.append(record)
            self._recent_syscalls = self._recent_syscalls[-100:]
