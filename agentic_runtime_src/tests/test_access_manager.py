from agentic_os.kernel.access import (
    AccessManager,
    AccessRequest,
    AccessResource,
    AccessSubject,
    AlwaysAllowTestInterventionProvider,
)


def test_owner_can_read_own_memory():
    manager = AccessManager()
    decision = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a"),
            action="read",
            resource=AccessResource("memory", "note_1", owner_agent="agent_a"),
        )
    )

    assert decision.allowed is True


def test_non_owner_cannot_read_private_memory():
    manager = AccessManager()
    decision = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_b"),
            action="read",
            resource=AccessResource("memory", "note_1", owner_agent="agent_a"),
        )
    )

    assert decision.allowed is False
    assert decision.error_code == "ACCESS_DENIED"


def test_shared_resource_read_allowed_write_denied():
    manager = AccessManager()
    resource = AccessResource("storage", "report_1", owner_agent="agent_a", labels=("shared",))
    reader = AccessSubject(agent_name="agent_b")

    assert manager.check(AccessRequest(reader, "read", resource)).allowed is True

    write_decision = manager.check(AccessRequest(reader, "write", resource))
    assert write_decision.allowed is False
    assert write_decision.error_code == "ACCESS_SHARED_WRITE_DENIED"


def test_delete_requires_intervention():
    manager = AccessManager()
    request = AccessRequest(
        subject=AccessSubject(agent_name="agent_a"),
        action="delete",
        resource=AccessResource("memory", "note_1", owner_agent="agent_a"),
    )

    decision = manager.check(request)

    assert decision.allowed is False
    assert decision.requires_intervention is True
    assert decision.error_code == "ACCESS_INTERVENTION_REQUIRED"


def test_delete_can_be_allowed_by_test_intervention_provider():
    manager = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    request = AccessRequest(
        subject=AccessSubject(agent_name="agent_a"),
        action="delete",
        resource=AccessResource("memory", "note_1", owner_agent="agent_a"),
    )

    decision = manager.check(request)

    assert decision.allowed is True
    assert decision.requires_intervention is True
    assert decision.intervention_id.startswith("ivn_")


def test_audit_delete_always_forbidden():
    manager = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    decision = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="admin_agent", groups=("admin",)),
            action="delete",
            resource=AccessResource("audit", "audit.jsonl", owner_agent="admin_agent"),
        )
    )

    assert decision.allowed is False
    assert decision.error_code == "ACCESS_AUDIT_DELETE_FORBIDDEN"


def test_robot_motion_requires_robot_operator_group():
    manager = AccessManager()
    resource = AccessResource("skill", "robot.navigate_to")

    denied = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a"),
            action="execute",
            resource=resource,
        )
    )
    allowed = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a", groups=("robot_operator",)),
            action="execute",
            resource=resource,
        )
    )

    assert denied.allowed is False
    assert denied.error_code == "ACCESS_ROBOT_OPERATOR_REQUIRED"
    assert allowed.allowed is True
