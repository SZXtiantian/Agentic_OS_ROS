from types import SimpleNamespace

from agentic_os.kernel.agent import (
    AgentCleanupManager,
    AgentCleanupStatus,
    AgentResourceRegistry,
    AgentResourceState,
    AgentTable,
    RuntimeCancellationAdapter,
    RuntimeResourceReleaseAdapter,
)


class FakeCancellationManager:
    def __init__(self):
        self.cancelled = []
        self.cleared = []

    def cancel_session(self, session_id):
        self.cancelled.append(session_id)

    def clear_session(self, session_id):
        self.cleared.append(session_id)


class FakeResourceManager:
    def __init__(self):
        self.agent_releases = []
        self.session_releases = []

    def release_by_agent(self, agent_id):
        self.agent_releases.append(agent_id)

    def release_by_session(self, session_id):
        self.session_releases.append(session_id)


class SessionOnlyResourceManager:
    def __init__(self):
        self.session_releases = []

    def release_by_session(self, session_id):
        self.session_releases.append(session_id)


def _runtime(resource_manager=None, cancellation_manager=None):
    return SimpleNamespace(
        executor=SimpleNamespace(
            resource_manager=resource_manager,
            cancellation_manager=cancellation_manager,
        )
    )


def _agent(table):
    return table.create("app_a", "sess_1", agent_id="agent_1")


def test_cleanup_manager_requests_runtime_cancellation():
    table = AgentTable()
    registry = AgentResourceRegistry()
    cancellation = FakeCancellationManager()
    cleanup = AgentCleanupManager(resource_registry=registry, agent_table=table)
    cleanup.register_cancellation_adapter(RuntimeCancellationAdapter(_runtime(cancellation_manager=cancellation)))
    agent = _agent(table)

    cleanup.request_running_cancellation(agent, reason="kill")
    cleanup.clear_agent_runtime_state(agent, reason="kill")

    assert cancellation.cancelled == ["sess_1"]
    assert cancellation.cleared == ["sess_1"]


def test_cleanup_manager_releases_runtime_resources_by_agent():
    table = AgentTable()
    registry = AgentResourceRegistry()
    resources = FakeResourceManager()
    cleanup = AgentCleanupManager(resource_registry=registry, agent_table=table)
    cleanup.register_resource_release_adapter(RuntimeResourceReleaseAdapter(_runtime(resource_manager=resources)))
    agent = _agent(table)
    handle = registry.register(agent_id=agent.agent_id, resource_type="skill_lock", resource_id="base")

    result = cleanup.release_agent_resources(agent, reason="exit")

    assert resources.agent_releases == [agent.agent_id]
    assert result["released_resources"] == [handle.handle_id]
    assert registry.require(handle.handle_id).state == AgentResourceState.RELEASED


def test_cleanup_manager_release_by_session_fallback():
    table = AgentTable()
    registry = AgentResourceRegistry()
    resources = SessionOnlyResourceManager()
    cleanup = AgentCleanupManager(resource_registry=registry, agent_table=table)
    cleanup.register_resource_release_adapter(RuntimeResourceReleaseAdapter(_runtime(resource_manager=resources)))
    agent = _agent(table)
    registry.register(agent_id=agent.agent_id, resource_type="skill_lock", resource_id="base")

    cleanup.release_agent_resources(agent, reason="exit")

    assert resources.session_releases == [agent.session_id]


def test_cleanup_is_idempotent():
    table = AgentTable()
    registry = AgentResourceRegistry()
    resources = FakeResourceManager()
    cleanup = AgentCleanupManager(resource_registry=registry, agent_table=table)
    cleanup.register_resource_release_adapter(RuntimeResourceReleaseAdapter(_runtime(resource_manager=resources)))
    agent = _agent(table)
    registry.register(agent_id=agent.agent_id, resource_type="skill_lock", resource_id="base")

    first = cleanup.cleanup_agent(agent, reason="exit")
    second = cleanup.cleanup_agent(agent, reason="exit")

    assert first.success is True
    assert second.success is True
    assert resources.agent_releases == [agent.agent_id]
    assert agent.cleanup_status == AgentCleanupStatus.COMPLETED


def test_cleanup_records_release_failed():
    table = AgentTable()
    registry = AgentResourceRegistry()
    cleanup = AgentCleanupManager(resource_registry=registry, agent_table=table)
    agent = _agent(table)
    handle = registry.register(agent_id=agent.agent_id, resource_type="skill_lock", resource_id="base")

    result = cleanup.cleanup_agent(agent, reason="kill")

    assert result.failed_resources == [handle.handle_id]
    assert registry.require(handle.handle_id).state == AgentResourceState.RELEASE_FAILED
    assert agent.cleanup_status == AgentCleanupStatus.FAILED
