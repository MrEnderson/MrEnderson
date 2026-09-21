"""Approval validity hardening (v0.1.3.3.1, narrow security patch). Closes
the loophole where an APPROVED-but-expired-or-consumed ApprovalRequest
could still authorize/consume. NO EXECUTION anywhere in this suite."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.database.models import PermissionLevel
from app.decision_intelligence.action_hash import compute_action_hash
from app.decision_intelligence.approval_engine import (
    ApprovalActionIdMismatchError,
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    ApprovalHashMismatchError,
    ApprovalNotApprovedError,
    advance_to_waiting_for_approval,
    assert_approval_valid,
    authorize_action,
    check_approval_validity,
    consume_approval,
    create_approval_request,
    decide_approval,
    expire_approval_request,
    validate_approval_for_action,
)
from app.decision_intelligence.permission_engine import apply_permission_decision, evaluate_permission
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


def _approved(**expiry_kwargs):
    registry = build_default_tool_registry()
    action = _validated_action()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent", **expiry_kwargs)
    waiting = advance_to_waiting_for_approval(checked)
    approved = decide_approval(request, "APPROVE", decided_by="human:alice")
    return waiting, approved


# --- 1/2/3/4: fresh vs expired, exact boundary --------------------------------


def test_fresh_approved_request_authorizes():
    waiting, approved = _approved()
    authorized = authorize_action(waiting, approved, now=approved.expires_at - timedelta(seconds=1))
    assert authorized.status == ActionStatus.APPROVED


def test_expired_approved_request_denied():
    waiting, approved = _approved()
    with pytest.raises(ApprovalExpiredError):
        authorize_action(waiting, approved, now=approved.expires_at + timedelta(seconds=1))


def test_exact_expires_at_equality_is_denied():
    waiting, approved = _approved()
    with pytest.raises(ApprovalExpiredError):
        authorize_action(waiting, approved, now=approved.expires_at)


def test_one_microsecond_before_expiration_is_allowed():
    waiting, approved = _approved()
    just_before = approved.expires_at - timedelta(microseconds=1)
    authorized = authorize_action(waiting, approved, now=just_before)
    assert authorized.status == ActionStatus.APPROVED


# --- 5-8: consumption validity -------------------------------------------------


def test_consumed_approval_denied_for_authorization():
    waiting, approved = _approved()
    consumed = consume_approval(approved, now=approved.expires_at - timedelta(seconds=1))
    with pytest.raises(ApprovalAlreadyConsumedError):
        authorize_action(waiting, consumed, now=approved.expires_at - timedelta(seconds=1))


def test_expired_approval_cannot_be_consumed():
    waiting, approved = _approved()
    with pytest.raises(ApprovalExpiredError):
        consume_approval(approved, now=approved.expires_at + timedelta(seconds=1))


def test_fresh_unconsumed_approval_can_be_consumed():
    waiting, approved = _approved()
    consumed = consume_approval(approved, now=approved.expires_at - timedelta(seconds=1))
    assert consumed.consumed is True
    assert consumed.consumed_at is not None


def test_second_consumption_denied():
    waiting, approved = _approved()
    just_before = approved.expires_at - timedelta(seconds=1)
    consumed = consume_approval(approved, now=just_before)
    with pytest.raises(ApprovalAlreadyConsumedError):
        consume_approval(consumed, now=just_before)


# --- 9-12: combinations must never short-circuit into accidental allow -------


def test_hash_match_plus_expired_denied():
    waiting, approved = _approved()
    assert compute_action_hash(waiting) == approved.action_hash  # hash is fine
    with pytest.raises(ApprovalExpiredError):
        authorize_action(waiting, approved, now=approved.expires_at + timedelta(seconds=1))


def test_hash_mismatch_plus_fresh_denied():
    waiting, approved = _approved()
    changed = waiting.model_copy(update={"tool_name": "content.publish"})
    fresh_now = approved.expires_at - timedelta(seconds=1)
    with pytest.raises(ApprovalHashMismatchError):
        authorize_action(changed, approved, now=fresh_now)


def test_correct_action_id_plus_expired_denied():
    waiting, approved = _approved()
    assert approved.action_id == waiting.id
    with pytest.raises(ApprovalExpiredError):
        authorize_action(waiting, approved, now=approved.expires_at + timedelta(seconds=1))


def test_wrong_action_id_plus_fresh_denied():
    waiting, approved = _approved()
    other_action = _validated_action()
    fresh_now = approved.expires_at - timedelta(seconds=1)
    with pytest.raises(ApprovalActionIdMismatchError):
        authorize_action(other_action, approved, now=fresh_now)


def test_expired_plus_hash_mismatch_denied():
    waiting, approved = _approved()
    changed = waiting.model_copy(update={"tool_name": "content.publish"})
    with pytest.raises((ApprovalHashMismatchError, ApprovalExpiredError)):
        authorize_action(changed, approved, now=approved.expires_at + timedelta(seconds=1))


# --- 13-16: non-approved statuses denied --------------------------------------


def test_rejected_request_denied_by_validity_check():
    registry = build_default_tool_registry()
    action = _validated_action()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    waiting = advance_to_waiting_for_approval(checked)
    rejected = decide_approval(request, "REJECT", decided_by="human:alice")
    result = check_approval_validity(rejected, waiting)
    assert result.valid is False
    assert "NOT_APPROVED" in result.reason_codes
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, rejected)


def test_cancelled_request_denied_by_validity_check():
    registry = build_default_tool_registry()
    action = _validated_action()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    waiting = advance_to_waiting_for_approval(checked)
    cancelled = decide_approval(request, "CANCEL", decided_by="human:alice")
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, cancelled)


def test_pending_request_denied_by_validity_check():
    registry = build_default_tool_registry()
    action = _validated_action()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    waiting = advance_to_waiting_for_approval(checked)
    result = check_approval_validity(request, waiting)
    assert result.valid is False
    assert "NOT_APPROVED" in result.reason_codes
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, request)


def test_expired_status_request_denied_by_validity_check():
    registry = build_default_tool_registry()
    action = _validated_action()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    waiting = advance_to_waiting_for_approval(checked)
    later = request.expires_at + timedelta(seconds=1)
    expired_status = expire_approval_request(request, now=later)
    result = check_approval_validity(expired_status, waiting, now=later)
    assert result.valid is False
    assert "NOT_APPROVED" in result.reason_codes
    with pytest.raises(ApprovalNotApprovedError):
        authorize_action(waiting, expired_status, now=later)


# --- 17/18: lifecycle vs security-relevant mutation before expiry ------------


def test_lifecycle_only_mutation_remains_valid_before_expiry():
    waiting, approved = _approved()
    changed = waiting.model_copy(update={"title": "A renamed title", "estimated_cost": 9.99})
    fresh_now = approved.expires_at - timedelta(seconds=1)
    result = validate_approval_for_action(approved, changed, now=fresh_now)
    assert result.valid is True


def test_security_relevant_mutation_denied_before_expiry():
    waiting, approved = _approved()
    changed = waiting.model_copy(update={"inputs": {"to": "attacker@example.com"}})
    fresh_now = approved.expires_at - timedelta(seconds=1)
    result = validate_approval_for_action(approved, changed, now=fresh_now)
    assert result.valid is False
    assert "HASH_MISMATCH" in result.reason_codes


# --- 19: injected time is fully deterministic ---------------------------------


def test_validity_check_is_deterministic_for_the_same_injected_now():
    waiting, approved = _approved()
    now = approved.expires_at - timedelta(minutes=1)
    first = check_approval_validity(approved, waiting, now=now)
    second = check_approval_validity(approved, waiting, now=now)
    assert first.valid == second.valid == True  # noqa: E712
    assert first.reason_codes == second.reason_codes == []


def test_validity_check_never_uses_wall_clock_when_now_is_injected():
    # A `now` far in the future must be respected exactly, never silently
    # clamped to "real" current time.
    waiting, approved = _approved()
    far_future = approved.expires_at + timedelta(days=3650)
    result = check_approval_validity(approved, waiting, now=far_future)
    assert result.valid is False
    assert "EXPIRED" in result.reason_codes


# --- 20: no execution / no tool invocation ------------------------------------


def test_validity_check_executes_nothing():
    waiting, approved = _approved()
    fresh_now = approved.expires_at - timedelta(seconds=1)
    before = build_default_tool_registry().list_definitions()
    check_approval_validity(approved, waiting, now=fresh_now)
    after = build_default_tool_registry().list_definitions()
    assert [t.name for t in before] == [t.name for t in after]
    assert waiting.result is None
    assert waiting.started_at is None


def test_consume_approval_does_not_execute_anything():
    waiting, approved = _approved()
    fresh_now = approved.expires_at - timedelta(seconds=1)
    consumed = consume_approval(approved, action=waiting, now=fresh_now)
    assert consumed.consumed is True
    assert waiting.result is None  # the Action itself is untouched


# --- 21: existing PENDING expiration behavior preserved ----------------------


def test_pending_expiration_still_transitions_to_expired_status():
    registry = build_default_tool_registry()
    action = _validated_action()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    request = create_approval_request(checked, decision, requested_by="planner-agent")
    later = request.expires_at + timedelta(seconds=1)
    expired = expire_approval_request(request, now=later)
    assert expired.status.value == "EXPIRED"


# --- Additional: validate_approval_for_action as the public gate -------------


def test_validate_approval_for_action_is_non_raising_and_structured():
    waiting, approved = _approved()
    expired_now = approved.expires_at + timedelta(seconds=1)
    result = validate_approval_for_action(approved, waiting, now=expired_now)
    assert result.valid is False
    assert "EXPIRED" in result.reason_codes
    assert isinstance(result.reason_codes, list)


def test_validate_approval_for_action_valid_true_when_all_checks_pass():
    waiting, approved = _approved()
    fresh_now = approved.expires_at - timedelta(seconds=1)
    result = validate_approval_for_action(approved, waiting, now=fresh_now)
    assert result.valid is True
    assert result.reason_codes == []


def test_authorize_action_default_now_uses_real_clock_and_still_denies_expired():
    # No injected `now` at all — falls back to real wall-clock time, which
    # must still correctly deny a request whose expires_at is in the past.
    waiting, approved = _approved(expires_at=approved_in_the_past())
    with pytest.raises(ApprovalExpiredError):
        authorize_action(waiting, approved)


def approved_in_the_past():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc) - timedelta(seconds=1)


# --- v0.1.3.4 preflight regression guard --------------------------------------


def test_action_none_never_reaches_an_action_dereferencing_reason_branch():
    """v0.1.3.4 preflight explicitly asked us to check
    _raise_for_validity_reason() for an unsafe `action=None` dereference
    before the ACTION_ID_MISMATCH/HASH_MISMATCH branches. Inspection: no
    defect exists — check_approval_validity() only ever appends those two
    reason codes when `action is not None` (see its `if action is not
    None and ...` guards), so assert_approval_valid(request, action=None)
    can never select a reason that dereferences `action.id`/
    compute_action_hash(action). This test locks that invariant in: every
    non-approved/consumed/expired status must still raise cleanly with
    action=None, never AttributeError/TypeError."""
    for status in (
        ApprovalRequestStatus.PENDING,
        ApprovalRequestStatus.REJECTED,
        ApprovalRequestStatus.EXPIRED,
        ApprovalRequestStatus.CANCELLED,
    ):
        request = ApprovalRequest(
            action_id="a1",
            permission_level=PermissionLevel.EXTERNAL_ACTION,
            action_hash="deadbeef",
            status=status,
        )
        with pytest.raises(ApprovalNotApprovedError):
            assert_approval_valid(request, None)


def test_check_approval_validity_accumulates_multiple_reasons():
    waiting, approved = _approved()
    changed = waiting.model_copy(update={"tool_name": "content.publish"})
    consumed = consume_approval(approved, now=approved.expires_at - timedelta(seconds=1))
    expired_now = approved.expires_at + timedelta(seconds=1)
    result = check_approval_validity(consumed, changed, now=expired_now)
    assert result.valid is False
    assert "HASH_MISMATCH" in result.reason_codes
    assert "ALREADY_CONSUMED" in result.reason_codes
    assert "EXPIRED" in result.reason_codes
