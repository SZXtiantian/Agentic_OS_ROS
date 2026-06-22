from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.capability import RobotCapabilityManager
from agentic_os.kernel.context import ContextManager
from agentic_os.kernel.hooks import InMemoryKernelEventSink, KernelQueueStore, sanitize_event_payload
from agentic_os.kernel.human import HumanInteractionManager
from agentic_os.kernel.llm_core import LLMAdapter, LLMConfig
from agentic_os.kernel.memory import MemoryManager
from agentic_os.kernel.scheduler import FIFOKernelScheduler, RoundRobinKernelScheduler
from agentic_os.kernel.storage import StorageManager
from agentic_os.kernel.system_call import KernelQuery, SyscallExecutionResult, SyscallExecutor
from agentic_os.kernel.tool import ToolManager
from agentic_runtime.kernel_service.robot_backend import RuntimeRobotCapabilityBackend


class KernelService:
    def __init__(self, runtime_server=None, config=None, audit_logger=None, managers: dict[str, Any] | None = None) -> None:
        self.runtime_server = runtime_server
        self.config = config or getattr(runtime_server, "config", None)
        self.audit_logger = audit_logger or getattr(runtime_server, "audit_logger", None)
        self.kernel_config = dict(getattr(self.config, "kernel", {}) or {})
        self.event_sink = InMemoryKernelEventSink()
        self.access_manager = AccessManager(event_sink=self.event_sink)
        self.queue_store = KernelQueueStore(event_sink=self.event_sink)
        self.llm = self._build_llm_adapter()
        self.context = self._build_context_manager()
        self.memory = self._build_memory_manager()
        self.storage = StorageManager(self._storage_root(), access_manager=self.access_manager)
        self.tool = self._build_tool_manager()
        robot_backend = RuntimeRobotCapabilityBackend(runtime_server) if runtime_server is not None else None
        self.robot_motion = RobotCapabilityManager(robot_backend)
        self.robot_sensor = RobotCapabilityManager(robot_backend)
        self.human = HumanInteractionManager()
        self.managers = {
            "llm": self.llm,
            "context": self.context,
            "memory": self.memory,
            "storage": self.storage,
            "tool": self.tool,
            "robot_motion": self.robot_motion,
            "robot_sensor": self.robot_sensor,
            "human": self.human,
            **dict(managers or {}),
        }
        self.scheduler = self._build_scheduler()
        self.executor = SyscallExecutor(queue_store=self.queue_store, event_sink=self.event_sink)
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
        if not self.scheduler.active:
            self.start()
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
            "manager_status": {name: self._manager_status(manager) for name, manager in sorted(self.managers.items())},
            "config": self._config_summary(),
            "access": {"policy": self.access_manager.policy.__class__.__name__},
            "audit": {"enabled": self.audit_logger is not None},
            "events": {"count": self.event_sink.count(), "recent": self.event_sink.recent(limit=25)},
            "llm": self._llm_status(),
            "context": self.context.status(),
            "memory": self.memory.status(),
            "storage": self._storage_status(),
            "tool": self.tool.status(),
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

    def _context_root(self) -> Path:
        context_config = dict(self.kernel_config.get("context") or {})
        if context_config.get("root"):
            root = Path(context_config["root"])
        else:
            root = self._storage_root() / ".kernel_context"
        if not root.is_absolute() and self.config is not None:
            root = Path(getattr(self.config, "repo_root", Path.cwd())) / root
        return root

    def _build_context_manager(self) -> ContextManager:
        context_config = dict(self.kernel_config.get("context") or {})
        manager = ContextManager(root=self._context_root())
        provider_status = manager.status()
        fail_fast = bool(context_config.get("fail_fast", False))
        if fail_fast and provider_status.get("state") != "ready":
            raise RuntimeError(str(provider_status))
        return manager

    def _build_llm_adapter(self) -> LLMAdapter:
        llm_config = dict(self.kernel_config.get("llm") or {})
        configs = list(llm_config.get("configs") or [{"name": "mock-kernel", "backend": "mock", "enabled": True}])
        routing_strategy = str(llm_config.get("routing_strategy") or "sequential")
        return LLMAdapter([LLMConfig.from_dict(config) if isinstance(config, dict) else config for config in configs], routing_strategy=routing_strategy)

    def _build_memory_manager(self) -> MemoryManager:
        memory_config = dict(self.kernel_config.get("memory") or {})
        db_path = memory_config.get("db_path") or (self._storage_root() / ".kernel_memory" / "memory.sqlite3")
        return MemoryManager(
            access_manager=self.access_manager,
            max_notes_per_agent=int(memory_config.get("max_notes", 100)),
            db_path=db_path,
        )

    def _build_tool_manager(self) -> ToolManager:
        tool_config = dict(self.kernel_config.get("tool") or {})
        tool_root = tool_config.get("tool_root") or getattr(self.config, "tool_root", None)
        if tool_root is not None and not Path(tool_root).is_absolute() and self.config is not None:
            tool_root = Path(getattr(self.config, "repo_root", Path.cwd())) / Path(tool_root)
        return ToolManager(tool_root=tool_root, access_manager=self.access_manager, event_sink=self.event_sink)

    def _build_scheduler(self):
        policy = str(self.kernel_config.get("scheduler_policy") or getattr(self.config, "scheduler_policy", "fifo")).lower()
        if policy in {"rr", "round_robin", "round-robin"}:
            return RoundRobinKernelScheduler(self.queue_store, self.managers, event_sink=self.event_sink)
        return FIFOKernelScheduler(self.queue_store, self.managers, event_sink=self.event_sink)

    def _config_summary(self) -> dict[str, Any]:
        llm_config = dict(self.kernel_config.get("llm") or {})
        configs = list(llm_config.get("configs") or [{"name": "mock-kernel", "backend": "mock", "enabled": True}])
        safe_llms = [
            {
                "name": str(item.get("name", "")) if isinstance(item, dict) else getattr(item, "name", ""),
                "backend": str(item.get("backend", "")) if isinstance(item, dict) else getattr(item, "backend", ""),
                "enabled": bool(item.get("enabled", True)) if isinstance(item, dict) else bool(getattr(item, "enabled", True)),
                "capabilities": list(item.get("capabilities", [])) if isinstance(item, dict) else list(getattr(item, "capabilities", ())),
            }
            for item in configs
        ]
        return {
            "scheduler_policy": str(self.kernel_config.get("scheduler_policy") or getattr(self.config, "scheduler_policy", "fifo")),
            "llm": {
                "routing_strategy": str(llm_config.get("routing_strategy") or "sequential"),
                "configs": safe_llms,
            },
            "tool": {
                "mcp_enabled": bool(dict(self.kernel_config.get("tool") or {}).get("mcp_enabled", False)),
            },
        }

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
            "syscall_id": result.syscall.syscall_id,
            "agent_name": agent_name,
            "operation_type": query.operation_type,
            "queue_name": queue_name,
            "manager_key": queue_name,
            "pid": result.metadata.get("pid"),
            "success": result.success,
            "status": status,
            "error_code": result.error_code,
            "duration_ms": duration_ms,
            "wait_ms": duration_ms,
        }
        if self.audit_logger is not None:
            audit_id = self.audit_logger.write(
                {
                    "app_id": agent_name,
                    "session_id": str(query.metadata.get("session_id", "kernel")),
                    "skill_name": f"kernel.{queue_name}.{query.operation_type}",
                    "args": self._safe_query_params(query),
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
            result.metadata["audit_id"] = audit_id
        result.metadata["syscall_id"] = result.syscall.syscall_id
        self.event_sink.emit(
            f"syscall.{ 'done' if result.success else 'failed' }",
            syscall_id=result.syscall.syscall_id,
            agent_name=agent_name,
            operation_type=query.operation_type,
            queue_name=queue_name,
            status=status,
            error_code=result.error_code,
            duration_ms=duration_ms,
            audit_id=record.get("audit_id", ""),
        )
        with self._recent_lock:
            self._recent_syscalls.append(record)
            self._recent_syscalls = self._recent_syscalls[-100:]

    def _safe_query_params(self, query: KernelQuery) -> dict[str, Any]:
        payload = dict(query.params)
        if hasattr(query, "messages"):
            payload["messages"] = getattr(query, "messages")
        return sanitize_event_payload(payload)

    def _manager_status(self, manager: Any) -> Any:
        if hasattr(manager, "status"):
            try:
                return manager.status()
            except Exception as exc:
                return {"status": "error", "error": str(exc)}
        return {"status": "ready"}

    def _llm_status(self) -> dict[str, Any]:
        return {"providers": self._config_summary()["llm"]["configs"]}

    def _storage_status(self) -> dict[str, Any]:
        return {"root": str(self._storage_root())}
