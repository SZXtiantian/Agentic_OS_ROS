from agentic_os.kernel.agent import (
    AgentCleanupStatus,
    AgentControlBlock,
    AgentExitKind,
    AgentResourceHandle,
    AgentResourceState,
    AgentStatus,
)


def test_acb_create_defaults():
    agent = AgentControlBlock.create(app_id="app_a", session_id="sess_1")

    assert agent.agent_id.startswith("agent_")
    assert agent.app_id == "app_a"
    assert agent.session_id == "sess_1"
    assert agent.agent_name == "app_a"
    assert agent.status == AgentStatus.CREATED
    assert agent.cleanup_status == AgentCleanupStatus.NOT_REQUIRED
    assert agent.exit_kind == AgentExitKind.NONE
    assert agent.owned_syscall_ids == []
    assert agent.running_syscall_ids == []
    assert agent.held_syscall_ids == []
    assert agent.resource_handle_ids == []
    assert agent.created_at


def test_acb_status_helpers():
    agent = AgentControlBlock.create(app_id="app_a", session_id="sess_1")
    assert agent.accepts_new_syscall() is False

    agent.mark_ready()
    assert agent.accepts_new_syscall() is True
    agent.mark_terminal(status=AgentStatus.EXITED, exit_kind=AgentExitKind.SUCCESS)

    assert agent.is_terminal() is True
    assert agent.is_dead() is True


def test_acb_attach_detach_syscall_idempotent():
    agent = AgentControlBlock.create(app_id="app_a", session_id="sess_1")

    agent.attach_syscall("ksc_1")
    agent.attach_syscall("ksc_1")
    agent.mark_syscall_running("ksc_1")
    agent.mark_syscall_running("ksc_1")
    agent.mark_syscall_held("ksc_1")
    agent.mark_syscall_held("ksc_1")

    assert agent.owned_syscall_ids == ["ksc_1"]
    assert agent.running_syscall_ids == []
    assert agent.held_syscall_ids == ["ksc_1"]

    agent.detach_syscall("ksc_1")
    agent.detach_syscall("ksc_1")

    assert agent.owned_syscall_ids == []
    assert agent.running_syscall_ids == []
    assert agent.held_syscall_ids == []


def test_acb_attach_detach_resource_idempotent():
    agent = AgentControlBlock.create(app_id="app_a", session_id="sess_1")

    agent.attach_resource("arh_1")
    agent.attach_resource("arh_1")
    assert agent.resource_handle_ids == ["arh_1"]

    agent.detach_resource("arh_1")
    agent.detach_resource("arh_1")
    assert agent.resource_handle_ids == []


def test_acb_to_dict_contains_lifecycle_and_ownership_fields():
    agent = AgentControlBlock.create(app_id="app_a", session_id="sess_1")
    agent.attach_syscall("ksc_1")
    agent.attach_resource("arh_1")

    payload = agent.to_dict()

    for key in {
        "agent_id",
        "app_id",
        "session_id",
        "status",
        "owned_syscall_ids",
        "running_syscall_ids",
        "held_syscall_ids",
        "resource_handle_ids",
        "cleanup_status",
        "exit_kind",
        "error_code",
        "created_at",
        "started_at",
        "ended_at",
        "reaped_at",
    }:
        assert key in payload


def test_resource_handle_to_dict_contains_release_state():
    handle = AgentResourceHandle(
        handle_id="arh_1",
        agent_id="agent_1",
        resource_type="skill_lock",
        resource_id="base",
    )
    handle.mark_release_pending("t1")
    handle.mark_released("t2")

    payload = handle.to_dict()

    assert payload["state"] == AgentResourceState.RELEASED
    assert payload["release_requested_at"] == "t1"
    assert payload["released_at"] == "t2"
