from __future__ import annotations

from threading import RLock
from typing import Any, Callable

from agentic_os.kernel.system_call.models import utc_now

from .errors import AGENT_ALREADY_EXISTS, AGENT_NOT_FOUND, AGENT_REAPED, AGENT_TRANSITION_INVALID, AgentLifecycleError
from .models import AgentControlBlock, AgentStatus


class AgentTable:
    def __init__(self, event_sink=None) -> None:
        self._agents: dict[str, AgentControlBlock] = {}
        self._tombstones: dict[str, AgentControlBlock] = {}
        self._lock = RLock()
        self.event_sink = event_sink

    def create(
        self,
        app_id: str,
        session_id: str,
        *,
        agent_name: str = "",
        parent_agent_id: str = "",
        created_by: str = "session_runner",
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
        agent_id: str = "",
    ) -> AgentControlBlock:
        agent = AgentControlBlock.create(
            app_id=app_id,
            session_id=session_id,
            agent_name=agent_name,
            parent_agent_id=parent_agent_id,
            created_by=created_by,
            priority=priority,
            metadata=metadata,
            agent_id=agent_id,
        )
        with self._lock:
            if agent.agent_id in self._agents or agent.agent_id in self._tombstones:
                raise AgentLifecycleError(AGENT_ALREADY_EXISTS, f"agent already exists: {agent.agent_id}")
            self._agents[agent.agent_id] = agent
            self._emit("agent.created", agent)
            return agent

    def get(self, agent_id: str, *, include_reaped: bool = False) -> AgentControlBlock | None:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is not None:
                return agent
            if include_reaped:
                return self._tombstones.get(agent_id)
            return None

    def require(self, agent_id: str, *, include_reaped: bool = False) -> AgentControlBlock:
        agent = self.get(agent_id, include_reaped=include_reaped)
        if agent is None:
            with self._lock:
                if agent_id in self._tombstones:
                    raise AgentLifecycleError(AGENT_REAPED, f"agent is reaped: {agent_id}")
            raise AgentLifecycleError(AGENT_NOT_FOUND, f"agent not found: {agent_id}")
        return agent

    def find_by_session(self, session_id: str) -> list[AgentControlBlock]:
        with self._lock:
            return [agent for agent in self._agents.values() if agent.session_id == session_id]

    def find_one_by_session(self, session_id: str, app_id: str = "") -> AgentControlBlock | None:
        with self._lock:
            for agent in self._agents.values():
                if agent.session_id == session_id and (not app_id or agent.app_id == app_id):
                    return agent
            return None

    def list(self, *, include_reaped: bool = False) -> list[AgentControlBlock]:
        with self._lock:
            agents = list(self._agents.values())
            if include_reaped:
                agents.extend(self._tombstones.values())
            return sorted(agents, key=lambda agent: (agent.created_at, agent.agent_id))

    def update(self, agent_id: str, mutator: Callable[[AgentControlBlock], None]) -> AgentControlBlock:
        with self._lock:
            agent = self.require(agent_id)
            mutator(agent)
            agent.touch()
            return agent

    def transition(
        self,
        agent_id: str,
        new_status: str,
        *,
        allowed_from: set[str] | None = None,
    ) -> AgentControlBlock:
        with self._lock:
            agent = self.require(agent_id)
            if allowed_from is not None and agent.status not in allowed_from:
                raise AgentLifecycleError(
                    AGENT_TRANSITION_INVALID,
                    f"cannot transition {agent_id} from {agent.status} to {new_status}",
                )
            agent.transition(new_status)
            self._emit(f"agent.{new_status}", agent)
            return agent

    def attach_syscall(self, agent_id: str, syscall_id: str) -> AgentControlBlock:
        return self.update(agent_id, lambda agent: agent.attach_syscall(syscall_id))

    def mark_syscall_running(self, agent_id: str, syscall_id: str) -> AgentControlBlock:
        return self.update(agent_id, lambda agent: agent.mark_syscall_running(syscall_id))

    def mark_syscall_held(self, agent_id: str, syscall_id: str) -> AgentControlBlock:
        return self.update(agent_id, lambda agent: agent.mark_syscall_held(syscall_id))

    def detach_syscall(self, agent_id: str, syscall_id: str) -> AgentControlBlock:
        return self.update(agent_id, lambda agent: agent.detach_syscall(syscall_id))

    def attach_resource(self, agent_id: str, handle_id: str) -> AgentControlBlock:
        return self.update(agent_id, lambda agent: agent.attach_resource(handle_id))

    def detach_resource(self, agent_id: str, handle_id: str) -> AgentControlBlock:
        return self.update(agent_id, lambda agent: agent.detach_resource(handle_id))

    def move_to_tombstone(self, agent_id: str) -> AgentControlBlock:
        with self._lock:
            agent = self.require(agent_id)
            self._agents.pop(agent_id, None)
            agent.reaped_at = agent.reaped_at or utc_now()
            agent.transition(AgentStatus.REAPED)
            self._tombstones[agent_id] = agent
            self._emit("agent.reaped", agent)
            return agent

    def snapshot(self, *, include_reaped: bool = False) -> dict[str, Any]:
        with self._lock:
            live = list(self._agents.values())
            tombstones = list(self._tombstones.values())
            items = live + (tombstones if include_reaped else [])
            return {
                "live_count": len(live),
                "terminal_count": sum(1 for agent in live if agent.status in AgentStatus.TERMINAL),
                "reaped_count": len(tombstones),
                "items": [agent.to_dict() for agent in sorted(items, key=lambda item: (item.created_at, item.agent_id))],
            }

    def _emit(self, event_type: str, agent: AgentControlBlock, **metadata: Any) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(
                event_type,
                agent_id=agent.agent_id,
                app_id=agent.app_id,
                session_id=agent.session_id,
                status=agent.status,
                **metadata,
            )
