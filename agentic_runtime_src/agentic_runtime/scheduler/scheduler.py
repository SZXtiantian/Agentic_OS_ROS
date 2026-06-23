from __future__ import annotations

import asyncio
from typing import Any

from agentic_os.kernel.scheduler import FIFORequestScheduler
from agentic_os.kernel.system_call import KernelSyscall, SyscallExecutor

from agentic_runtime.real_only import unsupported_task_field

from .session_runner import SessionRunner


class SingleRobotScheduler:
    def __init__(self, session_runner: SessionRunner) -> None:
        self.session_runner = session_runner
        self._lock = asyncio.Lock()
        self.kernel_executor = SyscallExecutor()
        self.kernel_executor.register("session", self._admit_session)
        self.kernel_scheduler = FIFORequestScheduler(self.kernel_executor)
        self.last_kernel_syscall_id = ""

    async def run_app(self, app_id: str, **kwargs: Any) -> dict[str, Any]:
        unsupported = unsupported_task_field(dict(kwargs))
        if unsupported is not None:
            return {"session_id": "", "app_id": app_id, "status": "failed", "result": unsupported}
        syscall = KernelSyscall.create(app_id, "session", "run_app", dict(kwargs))
        self.last_kernel_syscall_id = self.kernel_scheduler.submit(syscall)
        async with self._lock:
            self.kernel_scheduler.run_next()
            return await self.session_runner.run_app(app_id, **kwargs)

    def status(self) -> dict[str, Any]:
        status = self.kernel_scheduler.status()
        status["policy"] = "single_robot_fifo"
        status["active"] = self._lock.locked()
        status["last_kernel_syscall_id"] = self.last_kernel_syscall_id
        return status

    def _admit_session(self, syscall: KernelSyscall) -> dict[str, Any]:
        return {
            "accepted": True,
            "app_id": syscall.agent_name,
            "operation": syscall.operation_type,
            "params": syscall.params,
        }
