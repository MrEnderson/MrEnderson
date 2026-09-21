"""Deterministic Permission Engine contracts and security invariants
(v0.1.3.2, spec sections 5-13/17/21/22). NO REAL TOOL EXECUTION, NO
APPROVAL GRANTING anywhere in this suite."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.database.models import PermissionLevel, RiskLevel
from app.decision_intelligence.action_hash import compute_action_hash
from app.decision_intelligence.action_state_machine import (
    ActionTransitionError,
    can_transition,
)
from app.decision_intelligence.permission_engine import (
    PermissionDecision,
    PermissionOutcome,
    apply_permission_decision,
    evaluate_permission,
    max_permission,
    max_risk,
)
from app.decision_intelligence.schemas import Action, ActionStatus
from app.decision_intelligence.tool_registry import ToolRegistry, build_default_tool_registry


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1",
        action_type="read",
        title="do the thing",
        status=ActionStatus.VALIDATED,
    )
    fields.update(overrides)
    return Action(**fields)


@pytest.fixture
def registry() -> ToolRegistry:
    return build_default_tool_registry()


# --- P0: internal reasoning, no tool ----------------------------------------


def test_p0_internal_action_type_allows_without_tool(registry):
    action = _action(action_type="internal", tool_name=None)
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.ALLOW
    assert decision.permission_level == PermissionLevel.READ
    assert decision.tool_name is None
    assert "TOOL_ALLOWED" in decision.reason_codes


@pytest.mark.parametrize("action_type", ["no_op", "manual", "decision_only"])
def test_p0_covers_all_no_tool_action_types(registry, action_type):
    action = _action(action_type=action_type, tool_name=None)
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.ALLOW


# --- P1: read-only -----------------------------------------------------------


def test_p1_read_only_tool_allows(registry):
    action = _action(action_type="read", tool_name="research.read")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.ALLOW
    assert decision.permission_level == PermissionLevel.READ
    assert decision.approval_required is False


# --- P2: internal/sandboxed creation ----------------------------------------


def test_p2_internal_create_allows_with_audit(registry):
    action = _action(action_type="internal_create", tool_name="plan.create")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.ALLOW_WITH_AUDIT
    assert decision.permission_level == PermissionLevel.WRITE
    assert "AUDIT_REQUIRED" in decision.reason_codes


def test_p2_sandbox_create_allows_with_audit(registry):
    action = _action(action_type="sandbox_create", tool_name="file.create_sandboxed")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.ALLOW_WITH_AUDIT


# --- P3: reversible external change (policy-sensitive, conservative) --------


def test_p3_external_modify_requires_approval(registry):
    action = _action(action_type="external_modify", tool_name="mock.external_action")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.REQUIRE_APPROVAL
    assert decision.permission_level == PermissionLevel.EXTERNAL_ACTION
    assert decision.risk_level == RiskLevel.MEDIUM
    assert decision.approval_required is True


# --- P4: consequential external action --------------------------------------


@pytest.mark.parametrize(
    "action_type,tool_name",
    [
        ("send", "communication.send_email"),
        ("publish", "content.publish"),
        ("delete", "resource.delete_external"),
    ],
)
def test_p4_consequential_actions_require_approval(registry, action_type, tool_name):
    action = _action(action_type=action_type, tool_name=tool_name)
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.REQUIRE_APPROVAL
    assert decision.permission_level == PermissionLevel.EXTERNAL_ACTION
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.approval_required is True
    assert "HIGH_RISK" in decision.reason_codes


# --- P5: financial / privileged ----------------------------------------------


def test_p5_spend_money_requires_approval_not_ordinary_allow(registry):
    action = _action(action_type="financial", tool_name="finance.spend_money")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.REQUIRE_APPROVAL
    assert decision.permission_level == PermissionLevel.FINANCIAL_ACTION
    assert decision.risk_level == RiskLevel.CRITICAL
    assert decision.approval_required is True


def test_p5_install_software_blocks_by_default(registry):
    action = _action(action_type="install", tool_name="system.install_software")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert decision.permission_level == PermissionLevel.ADMIN


def test_p5_privileged_shell_blocks_by_default(registry):
    action = _action(action_type="privileged", tool_name="system.privileged_shell")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert decision.approval_required is False
    assert "FORBIDDEN_CAPABILITY" in decision.reason_codes


# --- Fail-closed: unknown tool / disabled tool / unsupported action type ----


def test_unknown_tool_blocks_with_reason_code(registry):
    # spec section 15's exact example.
    action = _action(action_type="privileged", tool_name="evil.magic_shell")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert "UNKNOWN_TOOL" in decision.reason_codes


def test_disabled_tool_blocks(registry):
    registry.register(
        registry.get("research.read").model_copy(update={"enabled": False}),
        replace=True,
    )
    action = _action(action_type="read", tool_name="research.read")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert "TOOL_DISABLED" in decision.reason_codes


def test_unsupported_action_type_for_tool_blocks(registry):
    action = _action(action_type="delete", tool_name="research.read")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert "UNSUPPORTED_ACTION_TYPE" in decision.reason_codes


def test_missing_tool_name_blocks(registry):
    action = _action(action_type="send", tool_name=None)
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert "MISSING_TOOL" in decision.reason_codes


def test_unknown_action_type_blocks(registry):
    action = _action(action_type="teleport_to_moon", tool_name="research.read")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert "UNSUPPORTED_ACTION_TYPE" in decision.reason_codes


def test_unknown_action_type_does_not_default_to_safe(registry):
    # Security test 14: unknown semantics must not default to P0/P1.
    action = _action(action_type="do_something_undefined", tool_name=None)
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert decision.permission_level != PermissionLevel.READ


# --- Permission floor / risk floor (spec section 7) -------------------------


def test_permission_floor_wins_over_lower_proposed_permission(registry):
    action = _action(
        action_type="send",
        tool_name="communication.send_email",
        permission_level=PermissionLevel.READ,  # agent claims P0/P1
    )
    decision = evaluate_permission(action, registry)
    assert decision.permission_level == PermissionLevel.EXTERNAL_ACTION
    assert decision.outcome == PermissionOutcome.REQUIRE_APPROVAL
    assert "PERMISSION_ESCALATED" in decision.reason_codes


def test_risk_floor_wins_over_lower_proposed_risk(registry):
    action = _action(
        action_type="send",
        tool_name="communication.send_email",
        risk_level=RiskLevel.LOW,  # agent claims LOW risk
    )
    decision = evaluate_permission(action, registry)
    assert decision.risk_level == RiskLevel.HIGH
    assert "RISK_ESCALATED" in decision.reason_codes


def test_proposed_permission_at_or_above_floor_is_not_flagged_as_escalated(registry):
    action = _action(
        action_type="read",
        tool_name="research.read",
        permission_level=PermissionLevel.ADMIN,  # over-cautious, not a downgrade
    )
    decision = evaluate_permission(action, registry)
    assert "PERMISSION_ESCALATED" not in decision.reason_codes
    # Authoritative value still comes from the tool/action floor, not the
    # agent's (higher) claim — the engine derives it, it doesn't just clamp.
    assert decision.permission_level == PermissionLevel.READ


def test_tool_default_permission_floor_beats_lower_action_type_floor(registry):
    # A tool that itself declares a higher floor than its action_type
    # alone would imply must not be downgraded by that action_type.
    registry.register(
        registry.get("research.read").model_copy(
            update={
                "name": "research.read_elevated",
                "default_permission_level": PermissionLevel.WRITE,
            }
        )
    )
    action = _action(action_type="read", tool_name="research.read_elevated")
    decision = evaluate_permission(action, registry)
    assert decision.permission_level == PermissionLevel.WRITE
    assert decision.outcome == PermissionOutcome.ALLOW_WITH_AUDIT


# --- max_permission / max_risk helpers ---------------------------------------


def test_max_permission_orders_all_five_levels():
    assert max_permission(PermissionLevel.READ, PermissionLevel.WRITE) == PermissionLevel.WRITE
    assert max_permission(PermissionLevel.ADMIN, PermissionLevel.READ) == PermissionLevel.ADMIN
    assert (
        max_permission(PermissionLevel.FINANCIAL_ACTION, PermissionLevel.EXTERNAL_ACTION)
        == PermissionLevel.FINANCIAL_ACTION
    )


def test_max_risk_orders_all_four_levels():
    assert max_risk(RiskLevel.LOW, RiskLevel.CRITICAL) == RiskLevel.CRITICAL
    assert max_risk(RiskLevel.HIGH, RiskLevel.MEDIUM) == RiskLevel.HIGH


# --- Structured outcome / reason codes (spec sections 5/17) -----------------


def test_outcome_is_never_a_bare_bool():
    action = _action(action_type="read", tool_name="research.read")
    decision = evaluate_permission(action, build_default_tool_registry())
    assert isinstance(decision.outcome, PermissionOutcome)
    assert not isinstance(decision, bool)


def test_reason_codes_are_structured_not_only_prose(registry):
    action = _action(action_type="read", tool_name="research.read")
    decision = evaluate_permission(action, registry)
    assert isinstance(decision.reason_codes, list)
    assert all(isinstance(code, str) and code.isupper() for code in decision.reason_codes)


def test_decision_carries_action_id_and_policy_source(registry):
    action = _action(action_type="read", tool_name="research.read")
    decision = evaluate_permission(action, registry)
    assert decision.action_id == action.id
    assert "permission_engine" in decision.policy_source
    assert decision.evaluated_at is not None


def test_decision_serialization_round_trips(registry):
    action = _action(action_type="send", tool_name="communication.send_email")
    decision = evaluate_permission(action, registry)
    dumped = decision.model_dump(mode="json")
    restored = PermissionDecision.model_validate(dumped)
    assert restored == decision


def test_unknown_permission_outcome_string_is_rejected():
    with pytest.raises(ValidationError):
        PermissionDecision(
            action_id="a1",
            outcome="MAYBE",
            permission_level=PermissionLevel.READ,
            risk_level=RiskLevel.LOW,
            approval_required=False,
        )


# --- Action-state integration (spec section 11) ------------------------------


def test_allow_transitions_validated_to_permission_checked(registry):
    action = _action(action_type="read", tool_name="research.read", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, registry)
    updated = apply_permission_decision(action, decision)
    assert updated.status == ActionStatus.PERMISSION_CHECKED
    assert updated.id == action.id


def test_block_transitions_validated_to_blocked(registry):
    action = _action(action_type="privileged", tool_name="system.privileged_shell", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, registry)
    updated = apply_permission_decision(action, decision)
    assert updated.status == ActionStatus.BLOCKED


def test_require_approval_still_reaches_permission_checked_not_executing(registry):
    action = _action(action_type="send", tool_name="communication.send_email", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, registry)
    updated = apply_permission_decision(action, decision)
    assert updated.status == ActionStatus.PERMISSION_CHECKED
    assert updated.approval_required is True


def test_apply_permission_decision_never_mutates_input(registry):
    action = _action(action_type="read", tool_name="research.read", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, registry)
    apply_permission_decision(action, decision)
    assert action.status == ActionStatus.VALIDATED  # original untouched


def test_apply_permission_decision_from_illegal_source_state_raises(registry):
    action = _action(action_type="read", tool_name="research.read", status=ActionStatus.PLANNED)
    decision = evaluate_permission(action, registry)
    with pytest.raises(ActionTransitionError):
        apply_permission_decision(action, decision)


def test_blocked_action_can_never_reach_executing(registry):
    # Security test 13: from BLOCKED, the only legal next state is CANCELLED.
    assert can_transition(ActionStatus.BLOCKED, ActionStatus.EXECUTING) is False
    assert can_transition(ActionStatus.BLOCKED, ActionStatus.CANCELLED) is True


def test_permission_checked_updates_authoritative_values_on_action(registry):
    action = _action(
        action_type="send",
        tool_name="communication.send_email",
        permission_level=PermissionLevel.READ,  # agent's dishonest/naive claim
        risk_level=RiskLevel.LOW,
        status=ActionStatus.VALIDATED,
    )
    decision = evaluate_permission(action, registry)
    updated = apply_permission_decision(action, decision)
    assert updated.permission_level == PermissionLevel.EXTERNAL_ACTION
    assert updated.risk_level == RiskLevel.HIGH


def test_action_hash_changes_when_authoritative_permission_is_applied(registry):
    # v0.1.3.1 compatibility: action_hash.py hashes permission_level/risk_level,
    # so overwriting them with authoritative values changes the fingerprint —
    # exactly as intended (a corrected security-relevant field must
    # invalidate any prior approval bound to the dishonest hash).
    action = _action(
        action_type="send",
        tool_name="communication.send_email",
        permission_level=PermissionLevel.READ,
        status=ActionStatus.VALIDATED,
    )
    before_hash = compute_action_hash(action)
    decision = evaluate_permission(action, registry)
    updated = apply_permission_decision(action, decision)
    after_hash = compute_action_hash(updated)
    assert before_hash != after_hash


# --- No execution, no approval granting (spec sections 9/12) ----------------


def test_require_approval_is_not_approved(registry):
    action = _action(action_type="send", tool_name="communication.send_email")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.REQUIRE_APPROVAL
    assert decision.outcome != PermissionOutcome.ALLOW
    assert not hasattr(decision, "approved")


def test_permission_decision_has_no_execution_side_effects(registry):
    action = _action(action_type="read", tool_name="research.read")
    before = registry.list_definitions()
    evaluate_permission(action, registry)
    after = registry.list_definitions()
    assert before == after  # registry untouched, nothing "ran"


def test_evaluate_permission_never_raises_for_a_malformed_but_valid_action(registry):
    # Every failure path returns BLOCK rather than propagating an exception,
    # so callers never need special-case exception handling.
    action = _action(action_type="", tool_name=None)
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK


# --- Malformed Action metadata fails closed at construction (Pydantic) ------


def test_malformed_permission_level_on_action_is_rejected_at_construction():
    with pytest.raises(ValidationError):
        Action(
            action_plan_id="plan-1",
            action_type="send",
            title="x",
            permission_level="ROOT",
        )


def test_malformed_risk_level_on_action_is_rejected_at_construction():
    with pytest.raises(ValidationError):
        Action(action_plan_id="plan-1", action_type="send", title="x", risk_level="EXTREME")


# --- Security invariants (spec section 22), explicit -------------------------


def test_security_1_agent_p0_claim_cannot_downgrade_tool_requiring_p4(registry):
    action = _action(
        action_type="send",
        tool_name="communication.send_email",
        permission_level=PermissionLevel.READ,
    )
    decision = evaluate_permission(action, registry)
    assert decision.permission_level == PermissionLevel.EXTERNAL_ACTION
    assert decision.outcome != PermissionOutcome.ALLOW


def test_security_2_agent_low_risk_claim_cannot_downgrade_tool_requiring_critical(registry):
    action = _action(
        action_type="financial",
        tool_name="finance.spend_money",
        risk_level=RiskLevel.LOW,
    )
    decision = evaluate_permission(action, registry)
    assert decision.risk_level == RiskLevel.CRITICAL


def test_security_3_unknown_tool_blocks(registry):
    action = _action(action_type="read", tool_name="totally.fake_tool")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK


def test_security_4_disabled_tool_blocks(registry):
    registry.register(registry.get("plan.create").model_copy(update={"enabled": False}), replace=True)
    action = _action(action_type="internal_create", tool_name="plan.create")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK


def test_security_5_unsupported_action_type_blocks(registry):
    action = _action(action_type="financial", tool_name="research.read")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK


def test_security_6_p4_never_ordinary_allow(registry):
    for action_type, tool_name in [
        ("send", "communication.send_email"),
        ("publish", "content.publish"),
        ("delete", "resource.delete_external"),
    ]:
        decision = evaluate_permission(_action(action_type=action_type, tool_name=tool_name), registry)
        assert decision.outcome in (PermissionOutcome.REQUIRE_APPROVAL, PermissionOutcome.BLOCK)


def test_security_7_p5_never_ordinary_allow(registry):
    for action_type, tool_name in [
        ("financial", "finance.spend_money"),
        ("install", "system.install_software"),
        ("privileged", "system.privileged_shell"),
    ]:
        decision = evaluate_permission(_action(action_type=action_type, tool_name=tool_name), registry)
        assert decision.outcome in (PermissionOutcome.REQUIRE_APPROVAL, PermissionOutcome.BLOCK)


def test_security_8_privileged_shell_blocks_by_default(registry):
    decision = evaluate_permission(
        _action(action_type="privileged", tool_name="system.privileged_shell"), registry
    )
    assert decision.outcome == PermissionOutcome.BLOCK


def test_security_9_malformed_permission_metadata_fails_closed():
    with pytest.raises(ValidationError):
        Action(action_plan_id="plan-1", action_type="read", title="x", permission_level="???")


def test_security_10_model_data_cannot_dynamically_register_executable_capability():
    registry = ToolRegistry()
    with pytest.raises(TypeError):
        registry.register({"name": "evil.tool", "supported_action_types": ["privileged"]})  # type: ignore[arg-type]
    assert registry.contains("evil.tool") is False


def test_security_11_successful_evaluation_executes_nothing(registry):
    action = _action(action_type="read", tool_name="research.read")
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.ALLOW
    # No result/output field ever appears on a PermissionDecision.
    assert not hasattr(decision, "result")
    assert not hasattr(decision, "output")


def test_security_12_require_approval_does_not_mean_approved(registry):
    decision = evaluate_permission(
        _action(action_type="delete", tool_name="resource.delete_external"), registry
    )
    assert decision.approval_required is True
    assert decision.outcome != PermissionOutcome.ALLOW
    assert decision.outcome != PermissionOutcome.ALLOW_WITH_AUDIT


def test_security_13_blocked_action_cannot_move_toward_executing(registry):
    action = _action(action_type="privileged", tool_name="system.privileged_shell", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, registry)
    updated = apply_permission_decision(action, decision)
    assert updated.status == ActionStatus.BLOCKED
    assert can_transition(ActionStatus.BLOCKED, ActionStatus.EXECUTING) is False


def test_security_14_unknown_action_semantics_cannot_default_to_safe(registry):
    decision = evaluate_permission(_action(action_type="frobnicate", tool_name=None), registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    assert decision.permission_level == PermissionLevel.ADMIN


def test_security_15_tool_permission_floor_always_wins_over_lower_proposed(registry):
    action = _action(
        action_type="install",
        tool_name="system.install_software",
        permission_level=PermissionLevel.READ,
        risk_level=RiskLevel.LOW,
    )
    decision = evaluate_permission(action, registry)
    assert decision.permission_level == PermissionLevel.ADMIN
    assert decision.risk_level == RiskLevel.CRITICAL
    assert decision.outcome == PermissionOutcome.BLOCK
