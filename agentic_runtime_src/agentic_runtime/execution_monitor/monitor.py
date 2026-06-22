from __future__ import annotations


class ExecutionMonitor:
    def __init__(self, audit_logger, resource_manager) -> None:
        self.audit_logger = audit_logger
        self.resource_manager = resource_manager

    def status(self, skills: list[str], ros_bridge: str = "cli") -> dict:
        return {
            "agenticd": "running",
            "ros_bridge": ros_bridge,
            "skills": [{"name": name, "status": "ready"} for name in skills],
            "resource_locks": self.resource_manager.snapshot(),
            "recent_syscalls": self.audit_logger.recent(limit=5),
        }
