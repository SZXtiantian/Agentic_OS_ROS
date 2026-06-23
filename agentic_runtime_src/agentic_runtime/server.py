from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.hooks import InMemoryKernelEventSink

from agentic_runtime.audit import AuditLogger
from agentic_runtime.app_factory import AppFactory
from agentic_runtime.config import RuntimeConfig
from agentic_runtime.config_manager import ConfigManager
from agentic_runtime.context_manager import ContextManager
from agentic_runtime.execution_monitor import ExecutionMonitor
from agentic_runtime.hardware_adapter import BridgeManager
from agentic_runtime.human_channel import FileHumanQueueChannel
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.llm import LLMChat
from agentic_runtime.memory import create_memory_manager
from agentic_runtime.permission_manager import PermissionManager
from agentic_runtime.ros_bridge_client.client import create_ros_bridge_client
from agentic_runtime.scheduler import SessionRunner, SingleRobotScheduler
from agentic_runtime.session import SessionManager, SessionStore
from agentic_runtime.simulation import simulated_backend_disabled
from agentic_runtime.skill_executor.cancellation import CancellationManager
from agentic_runtime.skill_executor.dispatcher import SkillDispatcher
from agentic_runtime.skill_executor.executor import SkillExecutor
from agentic_runtime.skill_executor.resource_manager import ResourceManager
from agentic_runtime.skill_registry import SkillRegistry
from agentic_runtime.storage import StorageManager
from agentic_runtime.syscall import SyscallStore
from agentic_runtime.task_log import TaskLogManager
from agentic_runtime.tool_manager import ToolManager


@dataclass
class RuntimeServer:
    config: RuntimeConfig
    registry: SkillRegistry
    executor: SkillExecutor
    monitor: ExecutionMonitor
    bridge_client: object
    audit_logger: AuditLogger
    session_manager: SessionManager
    syscall_store: SyscallStore
    storage_manager: StorageManager
    context_manager: ContextManager
    app_factory: AppFactory
    session_runner: SessionRunner
    scheduler: SingleRobotScheduler
    tool_manager: ToolManager
    config_manager: ConfigManager
    bridge_manager: BridgeManager
    kernel_service: KernelService
    task_log_manager: TaskLogManager
    llm_chat: LLMChat
    human_channel: FileHumanQueueChannel

    @classmethod
    def create(cls, mock: bool = False, bridge_client: object | None = None) -> "RuntimeServer":
        if mock:
            raise RuntimeError(simulated_backend_disabled("RuntimeServer.create(mock=True)")["error_code"])
        config_path = None
        if not os.environ.get("AGENTIC_RUNTIME_CONFIG"):
            candidate = Path("/opt/agentic/etc/agentic_robot.yaml")
            if candidate.exists():
                config_path = candidate
        config = RuntimeConfig.load(config_path)
        event_sink = InMemoryKernelEventSink()
        access_manager = AccessManager(event_sink=event_sink)
        registry = SkillRegistry(config.skill_root).load()
        audit_logger = AuditLogger(config.audit_log_path)
        memory_manager = create_memory_manager(
            config.memory_provider,
            config.memory_db_path,
            access_manager=access_manager,
            event_sink=event_sink,
        )
        session_store = SessionStore(config.session_root)
        session_manager = SessionManager(session_store)
        syscall_store = SyscallStore(config.session_root)
        resource_manager = ResourceManager()
        bridge_client = bridge_client or create_ros_bridge_client(config, mock=False)
        human_channel = FileHumanQueueChannel(config.session_root.parent / "human")
        dispatcher = SkillDispatcher(bridge_client, memory_manager, human_channel=human_channel)
        executor = SkillExecutor(
            registry=registry,
            permission_manager=PermissionManager(),
            resource_manager=resource_manager,
            dispatcher=dispatcher,
            audit_logger=audit_logger,
            cancellation_manager=CancellationManager(),
            syscall_store=syscall_store,
            session_manager=session_manager,
        )
        monitor = ExecutionMonitor(audit_logger, resource_manager)
        storage_manager = StorageManager(config.storage_root, access_manager=access_manager, event_sink=event_sink)
        context_manager = ContextManager(config.context_root, access_manager=access_manager, event_sink=event_sink)
        app_factory = AppFactory(config.app_root, executor)
        session_runner = SessionRunner(app_factory, session_manager, storage_manager, context_manager)
        scheduler = SingleRobotScheduler(session_runner)
        bridge_manager = BridgeManager(config.bridge_root, config.bridge_profile_root, capability_registry=registry.capabilities)
        tool_manager = ToolManager(audit_logger=audit_logger, access_manager=access_manager, event_sink=event_sink)
        config_manager = ConfigManager(config, registry)
        task_log_manager = TaskLogManager()
        llm_chat = LLMChat()
        server = cls(
            config=config,
            registry=registry,
            executor=executor,
            monitor=monitor,
            bridge_client=bridge_client,
            audit_logger=audit_logger,
            session_manager=session_manager,
            syscall_store=syscall_store,
            storage_manager=storage_manager,
            context_manager=context_manager,
            app_factory=app_factory,
            session_runner=session_runner,
            scheduler=scheduler,
            tool_manager=tool_manager,
            config_manager=config_manager,
            bridge_manager=bridge_manager,
            kernel_service=None,  # type: ignore[arg-type]
            task_log_manager=task_log_manager,
            llm_chat=llm_chat,
            human_channel=human_channel,
        )
        server.kernel_service = KernelService(server, access_manager=access_manager, event_sink=event_sink)
        server.executor.kernel_service = server.kernel_service
        server.executor.access_manager = server.kernel_service.access_manager
        server.executor.event_sink = server.kernel_service.event_sink
        return server

    def shutdown(self) -> None:
        self.kernel_service.stop()
