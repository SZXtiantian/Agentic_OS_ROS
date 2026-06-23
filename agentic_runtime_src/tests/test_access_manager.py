from agentic_os.kernel.access import (
    AccessDecision,
    AccessDecisionLog,
    AccessManager,
    AccessRequest,
    AccessResource,
    AccessRule,
    AccessSubject,
    AlwaysAllowTestInterventionProvider,
    FileQueueInterventionProvider,
    InMemoryAccessDecisionLog,
    InMemoryAccessStore,
    JsonFileAccessStore,
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


def test_external_llm_call_requires_permission_then_intervention():
    request_without_permission = AccessRequest(
        subject=AccessSubject(agent_name="agent_a"),
        action="execute",
        resource=AccessResource("llm", "external_provider", owner_agent="agent_a"),
        irreversible=True,
    )
    denied = AccessManager().check(request_without_permission)

    request_with_permission = AccessRequest(
        subject=AccessSubject(agent_name="agent_a", permissions=("llm.external.call",)),
        action="execute",
        resource=AccessResource("llm", "external_provider", owner_agent="agent_a"),
        irreversible=True,
    )
    intervention = AccessManager().check(request_with_permission)
    allowed = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider()).check(request_with_permission)

    assert denied.allowed is False
    assert denied.error_code == "ACCESS_DENIED"
    assert intervention.allowed is False
    assert intervention.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert intervention.requires_intervention is True
    assert allowed.allowed is True
    assert allowed.requires_intervention is True


def test_tool_management_requires_permission_then_intervention():
    request_without_permission = AccessRequest(
        subject=AccessSubject(agent_name="agent_a"),
        action="install",
        resource=AccessResource("tool", "sample.tool"),
        irreversible=True,
    )
    denied = AccessManager().check(request_without_permission)

    request_with_permission = AccessRequest(
        subject=AccessSubject(agent_name="agent_a", permissions=("tool.install",)),
        action="install",
        resource=AccessResource("tool", "sample.tool"),
        irreversible=True,
    )
    intervention = AccessManager().check(request_with_permission)
    allowed = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider()).check(request_with_permission)

    assert denied.allowed is False
    assert denied.error_code == "ACCESS_DENIED"
    assert intervention.allowed is False
    assert intervention.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert intervention.requires_intervention is True
    assert allowed.allowed is True
    assert allowed.requires_intervention is True


def test_tool_uninstall_and_register_builtin_are_high_risk_without_irreversible_flag():
    manager = AccessManager()

    uninstall = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a", permissions=("tool.uninstall",)),
            action="uninstall",
            resource=AccessResource("tool", "sample.tool"),
        )
    )
    register_builtin = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a", permissions=("tool.register_builtin",)),
            action="register_builtin",
            resource=AccessResource("tool", "calculator.add"),
        )
    )

    assert uninstall.allowed is False
    assert uninstall.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert uninstall.requires_intervention is True
    assert register_builtin.allowed is False
    assert register_builtin.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert register_builtin.requires_intervention is True


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


def test_dynamic_acl_can_allow_private_resource():
    store = InMemoryAccessStore(
        [
            AccessRule(
                subject_agent="agent_b",
                action="read",
                resource_type="memory",
                resource_id_pattern="note_*",
                effect="allow",
                reason="shared for review",
            )
        ]
    )
    manager = AccessManager(access_store=store)

    decision = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_b"),
            action="read",
            resource=AccessResource("memory", "note_1", owner_agent="agent_a"),
        )
    )

    assert decision.allowed is True
    assert decision.decision_id.startswith("acd_")
    assert decision.metadata["access_rule_effect"] == "allow"


def test_dynamic_acl_deny_overrides_owner_allow():
    store = InMemoryAccessStore(
        [
            AccessRule(
                subject_agent="agent_a",
                action="read",
                resource_type="memory",
                resource_id_pattern="note_secret",
                effect="deny",
                reason="sealed by operator",
            )
        ]
    )
    manager = AccessManager(access_store=store)

    decision = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a"),
            action="read",
            resource=AccessResource("memory", "note_secret", owner_agent="agent_a"),
        )
    )

    assert decision.allowed is False
    assert decision.error_code == "ACCESS_DYNAMIC_DENY"
    assert decision.reason == "sealed by operator"


def test_dynamic_acl_can_require_intervention():
    store = InMemoryAccessStore(
        [
            AccessRule(
                subject_group="operators",
                action="read",
                resource_type="storage",
                resource_id_pattern="reports/*",
                effect="require_intervention",
                reason="operator approval required",
            )
        ]
    )
    manager = AccessManager(access_store=store, intervention_provider=AlwaysAllowTestInterventionProvider())

    decision = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a", groups=("operators",)),
            action="read",
            resource=AccessResource("storage", "reports/today.md", owner_agent="agent_a"),
        )
    )

    assert decision.allowed is True
    assert decision.requires_intervention is True
    assert decision.metadata["access_rule_effect"] == "require_intervention"


def test_json_access_store_round_trips_rules(tmp_path):
    path = tmp_path / "acl.json"
    store = JsonFileAccessStore(path)
    store.add_rule(AccessRule(subject_agent="agent_b", action="read", resource_type="memory", effect="allow"))

    reloaded = JsonFileAccessStore(path)
    request = AccessRequest(
        subject=AccessSubject(agent_name="agent_b"),
        action="read",
        resource=AccessResource("memory", "note_1", owner_agent="agent_a"),
    )

    assert len(reloaded.list_rules()) == 1
    assert reloaded.matching_rules(request)[0].effect == "allow"


def test_decision_log_records_sanitized_metadata():
    class MetadataPolicy:
        def evaluate(self, request):
            return AccessDecision(allowed=True, reason="ok", metadata={"api_token": "secret", "safe": "ok"})

    decision_log = InMemoryAccessDecisionLog()
    manager = AccessManager(policy=MetadataPolicy(), decision_log=decision_log)

    decision = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a"),
            action="read",
            resource=AccessResource("memory", "note_1", owner_agent="agent_a"),
        )
    )

    assert decision.allowed is True
    assert decision_log.records[0]["decision_id"] == decision.decision_id
    assert decision_log.records[0]["metadata"] == {"api_token": "[REDACTED]", "safe": "ok"}


def test_file_queue_intervention_provider_writes_pending_request(tmp_path):
    queue_path = tmp_path / "interventions.jsonl"
    manager = AccessManager(intervention_provider=FileQueueInterventionProvider(queue_path))

    decision = manager.check(
        AccessRequest(
            subject=AccessSubject(agent_name="agent_a"),
            action="delete",
            resource=AccessResource("memory", "note_1", owner_agent="agent_a"),
        )
    )

    assert decision.allowed is False
    assert decision.requires_intervention is True
    assert decision.intervention_id.startswith("ivn_")
    assert '"ACCESS_INTERVENTION_REQUIRED"' in queue_path.read_text(encoding="utf-8")
