from __future__ import annotations

from dataclasses import replace

from agentic_os.kernel.hooks import KernelEventSink

from .decision_log import AccessDecisionLog, InMemoryAccessDecisionLog
from .intervention import DenyByDefaultInterventionProvider, InterventionProvider
from .policy import AccessDecision, AccessPolicy, AccessRequest, DefaultAccessPolicy, operation_key, requires_intervention
from .store import AccessRule, AccessStore, InMemoryAccessStore


HARD_STATIC_DENY_CODES = {
    "ACCESS_AUDIT_DELETE_FORBIDDEN",
    "ACCESS_ROBOT_OPERATOR_REQUIRED",
    "ACCESS_ROBOT_SENSOR_PERMISSION_REQUIRED",
    "ACCESS_SHARED_WRITE_DENIED",
}


class AccessManager:
    """Kernel access control layer for resources, sessions, and high-risk actions."""

    def __init__(
        self,
        policy: AccessPolicy | None = None,
        intervention_provider: InterventionProvider | None = None,
        access_store: AccessStore | None = None,
        decision_log: AccessDecisionLog | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.policy = policy or DefaultAccessPolicy()
        self.intervention_provider = intervention_provider or DenyByDefaultInterventionProvider()
        self.access_store = access_store or InMemoryAccessStore()
        self.decision_log = decision_log or InMemoryAccessDecisionLog()
        self.event_sink = event_sink

    def check(self, request: AccessRequest) -> AccessDecision:
        decision = self._evaluate(request)
        self.decision_log.record(request, decision)
        self._emit_checked(request, decision)
        return decision

    def _evaluate(self, request: AccessRequest) -> AccessDecision:
        decision = self.policy.evaluate(request)
        if self._is_hard_static_deny(decision):
            return decision

        rule = self._select_dynamic_rule(request)
        if rule is not None:
            return self._decision_from_rule(request, rule)

        if not decision.allowed:
            return decision

        if requires_intervention(request):
            return self._request_intervention(
                request,
                {"intervention_reason": "high_risk_operation", "operation": operation_key(request)},
            )
        return decision

    def assert_allowed(self, request: AccessRequest) -> None:
        decision = self.check(request)
        if not decision.allowed:
            raise PermissionError(f"{decision.error_code}: {decision.reason}")

    def add_rule(self, rule: AccessRule) -> None:
        self.access_store.add_rule(rule)

    def _select_dynamic_rule(self, request: AccessRequest) -> AccessRule | None:
        rules = self.access_store.matching_rules(request)
        for effect in ("deny", "require_intervention", "allow"):
            for rule in rules:
                if rule.effect == effect:
                    return rule
        return None

    def _decision_from_rule(self, request: AccessRequest, rule: AccessRule) -> AccessDecision:
        metadata = {
            "access_rule_effect": rule.effect,
            "access_rule_reason": rule.reason,
        }
        if rule.effect == "deny":
            return AccessDecision(
                allowed=False,
                error_code="ACCESS_DYNAMIC_DENY",
                reason=rule.reason or "dynamic access rule denied the request",
                metadata=metadata,
            )
        if rule.effect == "require_intervention":
            return self._request_intervention(request, metadata)

        decision = AccessDecision(
            allowed=True,
            reason=rule.reason or "dynamic access rule allowed the request",
            metadata=metadata,
        )
        if requires_intervention(request):
            return self._request_intervention(
                request,
                {**metadata, "intervention_reason": "high_risk_operation", "operation": operation_key(request)},
            )
        return decision

    def _request_intervention(self, request: AccessRequest, metadata: dict[str, str]) -> AccessDecision:
        decision = self.intervention_provider.request_confirmation(request)
        merged_metadata = {**decision.metadata, **metadata}
        return replace(decision, metadata=merged_metadata)

    def _is_hard_static_deny(self, decision: AccessDecision) -> bool:
        return bool(not decision.allowed and decision.error_code in HARD_STATIC_DENY_CODES)

    def _emit_checked(self, request: AccessRequest, decision: AccessDecision) -> None:
        if self.event_sink is not None:
            self.event_sink.emit(
                "access.checked",
                decision_id=decision.decision_id,
                agent_name=request.subject.agent_name,
                app_id=request.subject.app_id,
                action=request.action,
                resource_type=request.resource.resource_type,
                resource_id=request.resource.resource_id,
                allowed=decision.allowed,
                error_code=decision.error_code,
                requires_intervention=decision.requires_intervention,
            )
