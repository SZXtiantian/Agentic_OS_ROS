from agentic_os.kernel.agent import AgentResourceRegistry, AgentResourceState


def test_register_resource_handle():
    registry = AgentResourceRegistry()

    handle = registry.register(agent_id="agent_1", resource_type="skill_lock", resource_id="base")

    assert handle.handle_id.startswith("arh_")
    assert handle.agent_id == "agent_1"
    assert handle.state == AgentResourceState.ACQUIRED


def test_list_active_by_agent():
    registry = AgentResourceRegistry()
    active = registry.register(agent_id="agent_1", resource_type="skill_lock", resource_id="base")
    released = registry.register(agent_id="agent_1", resource_type="skill_lock", resource_id="arm")
    registry.register(agent_id="agent_2", resource_type="skill_lock", resource_id="base")
    registry.mark_released(released.handle_id)

    assert registry.list_active_by_agent("agent_1") == [active]


def test_mark_release_pending():
    registry = AgentResourceRegistry()
    handle = registry.register(agent_id="agent_1", resource_type="skill_lock", resource_id="base")

    registry.mark_release_pending(handle.handle_id)

    assert registry.require(handle.handle_id).state == AgentResourceState.RELEASE_PENDING


def test_mark_released():
    registry = AgentResourceRegistry()
    handle = registry.register(agent_id="agent_1", resource_type="skill_lock", resource_id="base")

    registry.mark_released(handle.handle_id)

    assert registry.require(handle.handle_id).state == AgentResourceState.RELEASED
    assert registry.require(handle.handle_id).release_error_code == ""


def test_mark_release_failed():
    registry = AgentResourceRegistry()
    handle = registry.register(agent_id="agent_1", resource_type="skill_lock", resource_id="base")

    registry.mark_release_failed(handle.handle_id, "AGENT_RESOURCE_RELEASE_FAILED", "boom")

    failed = registry.require(handle.handle_id)
    assert failed.state == AgentResourceState.RELEASE_FAILED
    assert failed.release_error_code == "AGENT_RESOURCE_RELEASE_FAILED"


def test_unregister_resource_is_admin_cleanup_not_normal_release():
    registry = AgentResourceRegistry()
    handle = registry.register(agent_id="agent_1", resource_type="skill_lock", resource_id="base")

    removed = registry.unregister(handle.handle_id)

    assert removed is handle
    assert registry.get(handle.handle_id) is None
