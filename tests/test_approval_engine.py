"""Human Approval Engine contracts and security invariants (v0.1.3.3, spec
sections 3-19/25/26). AUTHORIZATION ONLY — nothing here executes an Action,
invokes a tool, or bypasses the exact-action hash/action-ID binding."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.database.models import PermissionLevel, RiskLevel
from app.decision_intelligence.action_hash import compute_action_hash
from app.decision_intelligence.action_state_machine import ActionTransitionError
from app.decision_intelligence.approval_engine import (
    ActionApprovalMismatchError,
    ApprovalActionIdMismatchError,
    ApprovalAlreadyConsumedError,
    ApprovalAlreadyDecidedError,
    ApprovalHashMismatchError,
    ApprovalNotApprovedError,
    ApprovalNotExpirableError,
    ApprovalNotYetExpiredError,
    ApprovalOutcomeNotFinalError,
    InvalidActionStateForApprovalError,
    InvalidApprovalDecisionError,
    PermissionNotRequireApprovalError,
    SelfApprovalError,
    TrustedDecisionIdentityRequiredError,
    UnauthoritativeActionStateError,
    advance_to_waiting_for_approval,
    authorize_action,
    consume_approval,
    create_approval_request,
    decide_approval,
    expire_approval_request,
    finalize_action_from_approval_outcome,
    is_expired,
)
from app.decision_intelligence.permission_engine import (
    PermissionDecision,
    PermissionOutcome,
    apply_permission_decision,
    evaluate_permission,
)
from app.decision_intelligence.schemas import Action, ActionStatus, ApprovalRequest, ApprovalRequestStatus
from app.decision_intelligence.tool_registry import build_default_tool_registry


def _validated_action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1",
        action_type="send",
        tool_name="communication.send_email",
        title="Send the vendor email",
        expected_result="Vendor receives the email",
        inputs={"to": "vendor@example.com"},
        status=ActionStatus.VALIDATED,
    )
    fields.update(overrides)
    return Action(**fields)


def _permission_checked() -> tuple[Action, PermissionDecision]:
    registry = build_default_tool_registry()
    action = _validated_action()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    return checked, decision


def _waiting_for_approval() -> tuple[Action, ApprovalRequest]:
    checked, decision = _permission_checked()
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    waiting = advance_to_waiting_for_approval(checked)
    return waiting, request


def _approved_request(**decide_kwargs) -> tuple[Action, ApprovalRequest]:
    waiting, request = _waiting_for_approval()
    kwargs = dict(decided_by="human:alice")
    kwargs.update(decide_kwargs)
    approved = decide_approval(request, "APPROVE", **kwargs)
    return waiting, approved


# --- create_approval_request (spec section 4) --------------------------------


def test_create_approval_request_success():
    checked, decision = _permission_checked()
    request = create_approval_request(checked, decision, requested_by="planner-agent", reason="vendor invoice")
    assert request.status == ApprovalRequestStatus.PENDING
    assert request.action_id == checked.id
    assert request.permission_level == PermissionLevel.EXTERNAL_ACTION
    assert request.action_hash == compute_action_hash(checked)
    assert request.proposed_inputs == checked.inputs
    assert request.expected_effect == checked.expected_result
    assert request.consumed is False
    assert request.consumed_at is None


def test_create_approval_request_wrong_action_id_raises():
    checked, decision = _permission_checked()
    mismatched_decision = decision.model_copy(update={"action_id": "some-other-action"})
    with pytest.raises(ActionApprovalMismatchError):
        create_approval_request(checked, mismatched_decision, requested_by="planner-agent")


def test_create_approval_request_non_require_approval_outcome_rejected():
    registry = build_default_tool_registry()
    action = Action(
        action_plan_id="plan-1", action_type="read", tool_name="research.read", title="Read it", status=ActionStatus.VALIDATED
    )
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    assert decision.outcome == PermissionOutcome.ALLOW
    with pytest.raises(PermissionNotRequireApprovalError):
        create_approval_request(checked, decision, requested_by="planner-agent")


def test_create_approval_request_approval_required_flag_false_rejected():
    checked, decision = _permission_checked()
    inconsistent = decision.model_copy(update={"approval_required": False})
    with pytest.raises(PermissionNotRequireApprovalError):
        create_approval_request(checked, inconsistent, requested_by="planner-agent")


def test_create_approval_request_invalid_action_state_raises():
    action = _validated_action()  # still VALIDATED, not PERMISSION_CHECKED
    registry = build_default_tool_registry()
    decision = evaluate_permission(action, registry)
    with pytest.raises(InvalidActionStateForApprovalError):
        create_approval_request(action, decision, requested_by="planner-agent")


def test_create_approval_request_unauthoritative_action_state_raises():
    checked, decision = _permission_checked()
    # Simulate a caller that skipped apply_permission_decision(): the action
    # still carries the (correct-by-accident) authoritative values here, so
    # force a mismatch directly to prove the guard fires.
    stale = checked.model_copy(update={"permission_level": PermissionLevel.READ})
    with pytest.raises(UnauthoritativeActionStateError):
        create_approval_request(stale, decision, requested_by="planner-agent")


def test_create_approval_request_requires_nonempty_requested_by():
    checked, decision = _permission_checked()
    with pytest.raises(TrustedDecisionIdentityRequiredError):
        create_approval_request(checked, decision, requested_by="")


def test_create_approval_request_default_expiry_is_bounded():
    checked, decision = _permission_checked()
    before = datetime.now(timezone.utc)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    assert request.expires_at is not None
    assert request.expires_at > before
    assert request.expires_at <= before + timedelta(hours=24, minutes=1)


def test_create_approval_request_custom_expiry_override():
    checked, decision = _permission_checked()
    custom = datetime.now(timezone.utc) + timedelta(minutes=5)
    request = create_approval_request(checked, decision, requested_by="planner-agent", expires_at=custom)
    assert request.expires_at == custom


def test_create_approval_request_proposed_inputs_is_a_copy():
    checked, decision = _permission_checked()
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    request.proposed_inputs["to"] = "attacker@example.com"
    assert checked.inputs["to"] == "vendor@example.com"  # original untouched


def test_create_approval_request_p5_financial_classification_preserved():
    registry = build_default_tool_registry()
    action = Action(
        action_plan_id="plan-1",
        action_type="financial",
        tool_name="finance.spend_money",
        title="Pay the vendor invoice",
        status=ActionStatus.VALIDATED,
        expected_result="Vendor invoice paid",
    )
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    assert request.permission_level == PermissionLevel.FINANCIAL_ACTION
    assert "CRITICAL" in request.risk_summary


def test_create_approval_request_block_outcome_cannot_create_request():
    registry = build_default_tool_registry()
    action = Action(
        action_plan_id="plan-1",
        action_type="privileged",
        tool_name="system.privileged_shell",
        title="Run a shell command",
        status=ActionStatus.VALIDATED,
    )
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    blocked = apply_permission_decision(action, decision)
    assert blocked.status == ActionStatus.BLOCKED
    with pytest.raises(PermissionNotRequireApprovalError):
        create_approval_request(blocked, decision, requested_by="planner-agent")


def test_create_approval_request_admin_blocked_action_never_reaches_permission_checked():
    registry = build_default_tool_registry()
    action = Action(
        action_plan_id="plan-1", action_type="install", tool_name="system.install_software", title="Install a package", status=ActionStatus.VALIDATED
    )
    decision = evaluate_permission(action, registry)
    blocked = apply_permission_decision(action, decision)
    assert blocked.status == ActionStatus.BLOCKED
    assert blocked.status != ActionStatus.PERMISSION_CHECKED


def test_create_approval_request_cannot_be_downgraded_via_agent_proposed_level():
    # The agent originally proposed READ before permission evaluation ran;
    # by the time create_approval_request() sees the action, the engine has
    # already overwritten it to the authoritative EXTERNAL_ACTION floor.
    registry = build_default_tool_registry()
    action = _validated_action(permission_level=PermissionLevel.READ, risk_level=RiskLevel.LOW)
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    assert request.permission_level == PermissionLevel.EXTERNAL_ACTION


# --- advance_to_waiting_for_approval (spec section 5) -------------------------


def test_advance_to_waiting_for_approval_success():
    checked, _ = _permission_checked()
    waiting = advance_to_waiting_for_approval(checked)
    assert waiting.status == ActionStatus.WAITING_FOR_APPROVAL


def test_advance_to_waiting_for_approval_illegal_source_raises():
    action = _validated_action()  # VALIDATED, not PERMISSION_CHECKED
    with pytest.raises(ActionTransitionError):
        advance_to_waiting_for_approval(action)


def test_advance_to_waiting_for_approval_does_not_mutate_input():
    checked, _ = _permission_checked()
    advance_to_waiting_for_approval(checked)
    assert checked.status == ActionStatus.PERMISSION_CHECKED


# --- decide_approval (spec sections 6/10/18) ----------------------------------


def test_decide_approval_approve_success():
    _, request = _waiting_for_approval()
    approved = decide_approval(request, "APPROVE", decided_by="human:alice")
    assert approved.status == ApprovalRequestStatus.APPROVED
    assert approved.decided_by == "human:alice"
    assert approved.decided_at is not None


def test_decide_approval_reject_success():
    _, request = _waiting_for_approval()
    rejected = decide_approval(request, "REJECT", decided_by="human:alice")
    assert rejected.status == ApprovalRequestStatus.REJECTED


def test_decide_approval_cancel_success():
    _, request = _waiting_for_approval()
    cancelled = decide_approval(request, "CANCEL", decided_by="human:alice")
    assert cancelled.status == ApprovalRequestStatus.CANCELLED


def test_decide_approval_invalid_decision_string_raises():
    _, request = _waiting_for_approval()
    with pytest.raises(InvalidApprovalDecisionError):
        decide_approval(request, "EXPIRE", decided_by="human:alice")  # not a decide_approval decision


def test_decide_approval_requires_nonempty_decided_by():
    _, request = _waiting_for_approval()
    with pytest.raises(TrustedDecisionIdentityRequiredError):
        decide_approval(request, "APPROVE", decided_by="")


@pytest.mark.parametrize("first_decision", ["APPROVE", "REJECT", "CANCEL"])
def test_decide_approval_on_terminal_status_raises(first_decision):
    _, request = _waiting_for_approval()
    decided = decide_approval(request, first_decision, decided_by="human:bob")
    with pytest.raises(ApprovalAlreadyDecidedError):
        decide_approval(decided, "APPROVE", decided_by="human:alice")


def test_decide_approval_self_approval_blocked():
    _, request = _waiting_for_approval()
    assert request.requested_by == "planner-agent"
    with pytest.raises(SelfApprovalError):
        decide_approval(request, "APPROVE", decided_by="planner-agent")


def test_decide_approval_self_reject_is_allowed():
    _, request = _waiting_for_approval()
    rejected = decide_approval(request, "REJECT", decided_by="planner-agent")
    assert rejected.status == ApprovalRequestStatus.REJECTED


def test_decide_approval_self_cancel_is_allowed():
    _, request = _waiting_for_approval()
    cancelled = decide_approval(request, "CANCEL", decided_by="planner-agent")
    assert cancelled.status == ApprovalRequestStatus.CANCELLED


def test_decide_approval_does_not_mutate_input():
    _, request = _waiting_for_approval()
    decide_approval(request, "APPROVE", decided_by="human:alice")
    assert request.status == ApprovalRequestStatus.PENDING


# --- Terminal transitions explicitly forbidden (spec section 10) -------------


@pytest.mark.parametrize("terminal_decision", ["REJECT", "CANCEL"])
def test_terminal_statuses_cannot_be_reopened_to_approved(terminal_decision):
    _, request = _waiting_for_approval()
    terminal = decide_approval(request, terminal_decision, decided_by="human:alice")
    with pytest.raises(ApprovalAlreadyDecidedError):
        decide_approval(terminal, "APPROVE", decided_by="human:alice")


def test_expired_cannot_be_reopened_to_approved():
    _, request = _waiting_for_approval()
    later = request.expires_at + timedelta(seconds=1)
    expired = expire_approval_request(request, now=later)
    with pytest.raises(ApprovalAlreadyDecidedError):
        decide_approval(expired, "APPROVE", decided_by="human:alice")


# --- Expiration (spec sections 11/16) -----------------------------------------


def test_expire_approval_request_success():
    _, request = _waiting_for_approval()
    later = request.expires_at + timedelta(seconds=1)
    expired = expire_approval_request(request, now=later)
    assert expired.status == ApprovalRequestStatus.EXPIRED
    assert expired.decided_by == "system:expiration_policy"


def test_expire_approval_request_not_yet_expired_raises():
    _, request = _waiting_for_approval()
    earlier = request.expires_at - timedelta(seconds=1)
    with pytest.raises(ApprovalNotYetExpiredError):
        expire_approval_request(request, now=earlier)


def test_expire_approval_request_without_expiry_set_raises():
    request = ApprovalRequest(
        action_id="a1", permission_level=PermissionLevel.EXTERNAL_ACTION, action_hash="deadbeef"
    )
    assert request.expires_at is None
    with pytest.raises(ApprovalNotExpirableError):
        expire_approval_request(request)


def test_expire_approval_request_non_pending_raises():
    _, request = _waiting_for_approval()
    approved = decide_approval(request, "APPROVE", decided_by="human:alice")
    with pytest.raises(ApprovalAlreadyDecidedError):
        expire_approval_request(approved, now=approved.expires_at + timedelta(days=1) if approved.expires_at else None)


def test_is_expired_true_after_expiry():
    _, request = _waiting_for_approval()
    later = request.expires_at + timedelta(seconds=1)
    assert is_expired(request, now=later) is True


def test_is_expired_false_before_expiry():
    _, request = _waiting_for_approval()
    earlier = request.expires_at - timedelta(seconds=1)
    assert is_expired(request, now=earlier) is False


def test_is_expired_false_when_no_expiry_set():
    request = ApprovalRequest(
        action_id="a1", permission_level=PermissionLevel.EXTERNAL_ACTION, action_hash="deadbeef"
    )
    assert is_expired(request) is False


def test_expire_approval_request_does_not_mutate_input():
    _, request = _waiting_for_approval()
    later = request.expires_at + timedelta(seconds=1)
    expire_approval_request(request, now=later)
    assert request.status == ApprovalRequestStatus.PENDING


# --- authorize_action: exact-hash + action-ID binding (spec sections 7/8) ---


def test_authorize_action_success():
    waiting, approved = _approved_request()
    authorized = authorize_action(waiting, approved)
    assert authorized.status == ActionStatus.APPROVED


def test_authorize_action_requires_approved_status():
    waiting, request = _waiting_for_approval()  # still PENDING
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, request)


def test_authorize_action_wrong_action_id_raises():
    waiting, approved = _approved_request()
    other_action = _validated_action()  # a different Action entirely
    with pytest.raises(ApprovalActionIdMismatchError):
        authorize_action(other_action, approved)


def test_authorize_action_cannot_authorize_a_different_action_despite_matching_hash():
    # Security test 5: same exact payload/hash, different Action identity.
    waiting, approved = _approved_request()
    clone_with_same_payload = waiting.model_copy(update={"id": "a-completely-different-id"})
    assert compute_action_hash(clone_with_same_payload) == approved.action_hash
    with pytest.raises(ApprovalActionIdMismatchError):
        authorize_action(clone_with_same_payload, approved)


def test_authorize_action_tool_change_invalidates_approval():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"tool_name": "content.publish"})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)


def test_authorize_action_action_type_change_invalidates_approval():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"action_type": "publish"})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)


def test_authorize_action_inputs_change_invalidates_approval():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"inputs": {"to": "someone-else@example.com"}})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)


def test_authorize_action_expected_result_change_invalidates_approval():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"expected_result": "A completely different effect"})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)


def test_authorize_action_permission_level_change_invalidates_approval():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"permission_level": PermissionLevel.ADMIN})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "A totally different title"),
        ("description", "new description"),
        ("estimated_cost", 42.0),
        ("retry_count", 2),
    ],
)
def test_authorize_action_lifecycle_metadata_change_does_not_invalidate(field, value):
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={field: value})
    authorized = authorize_action(changed, approved)
    assert authorized.status == ActionStatus.APPROVED


def test_authorize_action_hash_mismatch_does_not_update_old_request():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"tool_name": "content.publish"})
    original_hash = approved.action_hash
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)
    assert approved.action_hash == original_hash  # untouched, not silently updated


def test_authorize_action_illegal_source_state_raises():
    waiting, approved = _approved_request()
    already_done = waiting.model_copy(update={"status": ActionStatus.COMPLETED})
    with pytest.raises(ActionTransitionError):
        authorize_action(already_done, approved)


def test_authorize_action_does_not_mutate_input():
    waiting, approved = _approved_request()
    authorize_action(waiting, approved)
    assert waiting.status == ActionStatus.WAITING_FOR_APPROVAL


def test_authorize_action_expired_approval_cannot_authorize():
    waiting, request = _waiting_for_approval()
    later = request.expires_at + timedelta(seconds=1)
    expired = expire_approval_request(request, now=later)
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, expired)


def test_authorize_action_rejected_approval_cannot_authorize():
    waiting, request = _waiting_for_approval()
    rejected = decide_approval(request, "REJECT", decided_by="human:alice")
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, rejected)


def test_authorize_action_cancelled_approval_cannot_authorize():
    waiting, request = _waiting_for_approval()
    cancelled = decide_approval(request, "CANCEL", decided_by="human:alice")
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, cancelled)


# --- finalize_action_from_approval_outcome (spec sections 14/15/16) ----------


def test_finalize_action_from_rejected():
    waiting, request = _waiting_for_approval()
    rejected = decide_approval(request, "REJECT", decided_by="human:alice")
    finalized = finalize_action_from_approval_outcome(waiting, rejected)
    assert finalized.status == ActionStatus.REJECTED


def test_finalize_action_from_cancelled():
    waiting, request = _waiting_for_approval()
    cancelled = decide_approval(request, "CANCEL", decided_by="human:alice")
    finalized = finalize_action_from_approval_outcome(waiting, cancelled)
    assert finalized.status == ActionStatus.CANCELLED


def test_finalize_action_from_expired_maps_to_cancelled():
    waiting, request = _waiting_for_approval()
    later = request.expires_at + timedelta(seconds=1)
    expired = expire_approval_request(request, now=later)
    finalized = finalize_action_from_approval_outcome(waiting, expired)
    assert finalized.status == ActionStatus.CANCELLED


@pytest.mark.parametrize("status", [ApprovalRequestStatus.PENDING, ApprovalRequestStatus.APPROVED])
def test_finalize_action_rejects_non_terminal_status(status):
    waiting, request = _waiting_for_approval()
    non_terminal = request.model_copy(update={"status": status})
    with pytest.raises(ApprovalOutcomeNotFinalError):
        finalize_action_from_approval_outcome(waiting, non_terminal)


def test_finalize_action_wrong_action_id_raises():
    waiting, request = _waiting_for_approval()
    rejected = decide_approval(request, "REJECT", decided_by="human:alice")
    other_action = _validated_action()
    with pytest.raises(ApprovalActionIdMismatchError):
        finalize_action_from_approval_outcome(other_action, rejected)


def test_finalize_action_illegal_source_state_raises():
    waiting, request = _waiting_for_approval()
    rejected = decide_approval(request, "REJECT", decided_by="human:alice")
    already_done = waiting.model_copy(update={"status": ActionStatus.COMPLETED})
    with pytest.raises(ActionTransitionError):
        finalize_action_from_approval_outcome(already_done, rejected)


def test_finalize_action_does_not_mutate_input():
    waiting, request = _waiting_for_approval()
    rejected = decide_approval(request, "REJECT", decided_by="human:alice")
    finalize_action_from_approval_outcome(waiting, rejected)
    assert waiting.status == ActionStatus.WAITING_FOR_APPROVAL


# --- consume_approval / double-use protection (spec sections 12/13) ----------


def test_consume_approval_success():
    _, approved = _approved_request()
    consumed = consume_approval(approved)
    assert consumed.consumed is True
    assert consumed.consumed_at is not None


def test_consume_approval_requires_approved_status():
    _, request = _waiting_for_approval()  # PENDING
    with pytest.raises(ApprovalNotApprovedError):
        consume_approval(request)


def test_consume_approval_double_consumption_blocked():
    _, approved = _approved_request()
    consumed = consume_approval(approved)
    with pytest.raises(ApprovalAlreadyConsumedError):
        consume_approval(consumed)


def test_consume_approval_does_not_mutate_input():
    _, approved = _approved_request()
    consume_approval(approved)
    assert approved.consumed is False


# --- Structural / serialization ----------------------------------------------


def test_approval_request_serialization_round_trips_new_fields():
    checked, decision = _permission_checked()
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    dumped = request.model_dump(mode="json")
    restored = ApprovalRequest.model_validate(dumped)
    assert restored == request


def test_approval_request_status_enum_unchanged_from_v0131():
    assert {member.value for member in ApprovalRequestStatus} == {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "EXPIRED",
        "CANCELLED",
    }


def test_malformed_approval_status_string_rejected_at_construction():
    with pytest.raises(ValidationError):
        ApprovalRequest(
            action_id="a1",
            permission_level=PermissionLevel.EXTERNAL_ACTION,
            action_hash="deadbeef",
            status="MAYBE",
        )


def test_approval_request_defaults_not_consumed():
    request = ApprovalRequest(
        action_id="a1", permission_level=PermissionLevel.EXTERNAL_ACTION, action_hash="deadbeef"
    )
    assert request.consumed is False
    assert request.consumed_at is None
    assert request.expires_at is None


# --- No execution anywhere (spec sections 9/12/14/15, security 14/15) -------


def test_authorize_action_produces_no_result_or_output():
    waiting, approved = _approved_request()
    authorized = authorize_action(waiting, approved)
    assert authorized.result is None
    assert authorized.error is None


def test_approval_engine_module_has_no_execution_or_tool_registry_import():
    import app.decision_intelligence.approval_engine as module

    assert not hasattr(module, "ToolRegistry")
    assert not hasattr(module, "execute")
    assert not hasattr(module, "run_tool")


def test_require_approval_alone_is_insufficient_for_approved_action():
    # Security test 11/17 of v0.1.3.2 review: REQUIRE_APPROVAL by itself
    # never becomes ActionStatus.APPROVED without the full chain.
    checked, decision = _permission_checked()
    assert decision.outcome == PermissionOutcome.REQUIRE_APPROVAL
    assert checked.status == ActionStatus.PERMISSION_CHECKED
    assert checked.status != ActionStatus.APPROVED


# --- Security invariants (spec section 26), explicit --------------------------


def test_security_1_agent_cannot_approve_its_own_request():
    _, request = _waiting_for_approval()
    with pytest.raises(SelfApprovalError):
        decide_approval(request, "APPROVE", decided_by=request.requested_by)


def test_security_2_changed_action_payload_invalidates_approval():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"inputs": {"to": "different@example.com"}})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)


def test_security_3_changed_tool_invalidates_approval():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"tool_name": "resource.delete_external"})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)


def test_security_4_changed_inputs_invalidate_approval():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"inputs": {}})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)


def test_security_5_approval_for_action_a_cannot_authorize_action_b():
    waiting, approved = _approved_request()
    action_b = _validated_action()
    with pytest.raises(ApprovalActionIdMismatchError):
        authorize_action(action_b, approved)


def test_security_6_expired_approval_cannot_authorize():
    waiting, request = _waiting_for_approval()
    expired = expire_approval_request(request, now=request.expires_at + timedelta(seconds=1))
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, expired)


def test_security_7_rejected_approval_cannot_authorize():
    waiting, request = _waiting_for_approval()
    rejected = decide_approval(request, "REJECT", decided_by="human:alice")
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, rejected)


def test_security_8_cancelled_approval_cannot_authorize():
    waiting, request = _waiting_for_approval()
    cancelled = decide_approval(request, "CANCEL", decided_by="human:alice")
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, cancelled)


def test_security_9_consumed_approval_cannot_authorize_again():
    waiting, approved = _approved_request()
    consume_approval(approved)  # marks consumed on the returned copy only
    consumed = consume_approval(approved)
    with pytest.raises(ApprovalAlreadyConsumedError):
        consume_approval(consumed)


def test_security_10_block_permission_cannot_create_approval_request():
    registry = build_default_tool_registry()
    action = Action(
        action_plan_id="plan-1", action_type="privileged", tool_name="system.privileged_shell", title="Run a shell command", status=ActionStatus.VALIDATED
    )
    decision = evaluate_permission(action, registry)
    blocked = apply_permission_decision(action, decision)
    with pytest.raises(PermissionNotRequireApprovalError):
        create_approval_request(blocked, decision, requested_by="planner-agent")


def test_security_11_require_approval_alone_cannot_produce_approved_action():
    checked, decision = _permission_checked()
    assert decision.outcome == PermissionOutcome.REQUIRE_APPROVAL
    assert checked.status != ActionStatus.APPROVED


def test_security_12_approval_cannot_downgrade_authoritative_permission():
    registry = build_default_tool_registry()
    action = _validated_action(permission_level=PermissionLevel.READ)
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    assert request.permission_level == PermissionLevel.EXTERNAL_ACTION
    assert request.permission_level != PermissionLevel.READ


@pytest.mark.parametrize("start_decision", ["REJECT", "CANCEL"])
def test_security_13_terminal_approval_status_cannot_be_reopened(start_decision):
    _, request = _waiting_for_approval()
    terminal = decide_approval(request, start_decision, decided_by="human:alice")
    with pytest.raises(ApprovalAlreadyDecidedError):
        decide_approval(terminal, "APPROVE", decided_by="human:alice")


def test_security_14_approval_does_not_execute_the_action():
    waiting, approved = _approved_request()
    authorized = authorize_action(waiting, approved)
    # Only status changed — no execution-shaped fields were populated.
    assert authorized.result is None
    assert authorized.started_at is None
    assert authorized.completed_at is None


def test_security_15_approval_does_not_invoke_tool_registry_execution():
    import inspect

    from app.decision_intelligence import approval_engine

    source = inspect.getsource(approval_engine)
    assert "registry.resolve" not in source
    assert ".search(" not in source
    assert ".fetch(" not in source


def test_security_16_admin_blocked_action_cannot_enter_approval_flow():
    registry = build_default_tool_registry()
    action = Action(
        action_plan_id="plan-1", action_type="install", tool_name="system.install_software", title="Install a package", status=ActionStatus.VALIDATED
    )
    decision = evaluate_permission(action, registry)
    blocked = apply_permission_decision(action, decision)
    assert blocked.status == ActionStatus.BLOCKED
    with pytest.raises(InvalidActionStateForApprovalError):
        # Even if outcome were mis-checked, the action-state guard alone stops it.
        create_approval_request(
            blocked, decision.model_copy(update={"outcome": PermissionOutcome.REQUIRE_APPROVAL, "approval_required": True}), requested_by="planner-agent"
        )


def test_security_17_hash_mismatch_requires_new_approval_not_silent_update():
    waiting, approved = _approved_request()
    changed = waiting.model_copy(update={"expected_result": "Something else entirely"})
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved)
    # The only recovery path is a brand new request from the current payload.
    registry = build_default_tool_registry()
    new_decision = evaluate_permission(changed.model_copy(update={"status": ActionStatus.VALIDATED}), registry)
    re_checked = apply_permission_decision(changed.model_copy(update={"status": ActionStatus.VALIDATED}), new_decision)
    new_request = create_approval_request(re_checked, new_decision, requested_by="planner-agent")
    assert new_request.id != approved.id
    assert new_request.action_hash == compute_action_hash(re_checked)


def test_security_18_malformed_approval_state_fails_closed():
    with pytest.raises(ValidationError):
        ApprovalRequest(
            action_id="a1",
            permission_level="ROOT",  # not a real PermissionLevel
            action_hash="deadbeef",
        )
