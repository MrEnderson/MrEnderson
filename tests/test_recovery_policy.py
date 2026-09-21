"""Deterministic Recovery Policy (v0.1.3.7, spec sections 7/8/12). Pure
function tests — no database, no I/O."""
from __future__ import annotations

import pytest

from app.decision_intelligence.recovery_policy import RecoveryDecision, evaluate_recovery
from app.decision_intelligence.schemas import FailureCategory


def _eval(**overrides):
    fields = dict(
        category=FailureCategory.TRANSIENT, side_effect_occurred=False, retry_count=0, max_retries=1,
        approval_required=False,
    )
    fields.update(overrides)
    return evaluate_recovery(**fields)


class TestFailureDoesNotImplyRetry:
    def test_security_never_retries_even_with_budget(self):
        result = _eval(category=FailureCategory.SECURITY, retry_count=0, max_retries=100)
        assert result.decision == RecoveryDecision.SECURITY_BLOCKED
        assert result.retry_permitted is False

    def test_permission_never_retries(self):
        result = _eval(category=FailureCategory.PERMISSION, retry_count=0, max_retries=100)
        assert result.decision == RecoveryDecision.STOP
        assert result.retry_permitted is False

    def test_approval_never_becomes_execution(self):
        result = _eval(category=FailureCategory.APPROVAL, retry_count=0, max_retries=100)
        assert result.decision == RecoveryDecision.STOP
        assert result.retry_permitted is False

    def test_budget_category_always_stops(self):
        result = _eval(category=FailureCategory.BUDGET)
        assert result.decision == RecoveryDecision.BUDGET_EXHAUSTED


class TestTransientRetry:
    def test_retry_when_side_effect_absent_and_budget_available(self):
        result = _eval(category=FailureCategory.TRANSIENT, side_effect_occurred=False, retry_count=0, max_retries=2)
        assert result.decision == RecoveryDecision.RETRY
        assert result.retry_permitted is True
        assert "SIDE_EFFECT_KNOWN_ABSENT" in result.reason_codes

    def test_reconcile_when_side_effect_may_have_occurred(self):
        result = _eval(category=FailureCategory.TRANSIENT, side_effect_occurred=True, retry_count=0, max_retries=2)
        assert result.decision == RecoveryDecision.RECONCILE
        assert result.retry_permitted is False

    def test_budget_exhausted_at_retry_count_equal_max(self):
        result = _eval(category=FailureCategory.TRANSIENT, retry_count=2, max_retries=2)
        assert result.decision == RecoveryDecision.BUDGET_EXHAUSTED

    def test_budget_exhausted_when_retry_count_exceeds_max(self):
        result = _eval(category=FailureCategory.TRANSIENT, retry_count=5, max_retries=2)
        assert result.decision == RecoveryDecision.BUDGET_EXHAUSTED

    def test_one_below_max_still_retries(self):
        result = _eval(category=FailureCategory.TRANSIENT, retry_count=1, max_retries=2)
        assert result.decision == RecoveryDecision.RETRY

    def test_zero_max_retries_never_retries(self):
        result = _eval(category=FailureCategory.TRANSIENT, retry_count=0, max_retries=0)
        assert result.decision == RecoveryDecision.BUDGET_EXHAUSTED


class TestToolRetry:
    def test_retry_when_side_effect_absent(self):
        result = _eval(category=FailureCategory.TOOL, side_effect_occurred=False, retry_count=0, max_retries=1)
        assert result.decision == RecoveryDecision.RETRY

    def test_reconcile_when_side_effect_present(self):
        result = _eval(category=FailureCategory.TOOL, side_effect_occurred=True)
        assert result.decision == RecoveryDecision.RECONCILE


class TestApprovalRequiredOverride:
    """An approval-gated Action's single-use approval is already consumed
    — no category ever auto-retries it (spec sections 12/13 of v0.1.3.3.1)."""

    @pytest.mark.parametrize("category", [FailureCategory.TRANSIENT, FailureCategory.TOOL])
    def test_transient_and_tool_become_human_review_when_approval_required(self, category):
        result = _eval(category=category, side_effect_occurred=False, retry_count=0, max_retries=5, approval_required=True)
        assert result.decision == RecoveryDecision.HUMAN_REVIEW
        assert result.retry_permitted is False


class TestValidationCategory:
    def test_validation_is_replan_candidate_by_default(self):
        result = _eval(category=FailureCategory.VALIDATION)
        assert result.decision == RecoveryDecision.REPLAN
        assert result.replan_permitted is True

    def test_validation_stops_when_replan_budget_exhausted(self):
        result = _eval(category=FailureCategory.VALIDATION, replan_permitted=False)
        assert result.decision == RecoveryDecision.STOP


class TestVerificationCategory:
    def test_verification_always_reconciles_first(self):
        result = _eval(category=FailureCategory.VERIFICATION, side_effect_occurred=True)
        assert result.decision == RecoveryDecision.RECONCILE
        # Even with a "clean" absent side effect, VERIFICATION never
        # auto-retries execution merely because verification failed.
        result2 = _eval(category=FailureCategory.VERIFICATION, side_effect_occurred=False)
        assert result2.decision == RecoveryDecision.RECONCILE


class TestUnknownCategory:
    def test_unknown_never_blindly_retries(self):
        result = _eval(category=FailureCategory.UNKNOWN, side_effect_occurred=False, retry_count=0, max_retries=5)
        assert result.decision != RecoveryDecision.RETRY
        assert result.decision == RecoveryDecision.RECONCILE
        assert "UNKNOWN_NEVER_BLINDLY_RETRIES" in result.reason_codes


class TestStructuredResult:
    def test_result_always_has_reason_codes(self):
        for category in FailureCategory:
            result = _eval(category=category)
            assert result.reason_codes, f"{category} produced no reason codes"

    def test_decision_is_never_a_bare_bool(self):
        result = _eval()
        assert isinstance(result.decision, RecoveryDecision)
