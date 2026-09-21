"""Decision domain contract: construction, readiness invariants, the
Decision state machine, and the Decision -> ActionPlan boundary (v0.1.3.1,
spec sections 3 and 14)."""
from __future__ import annotations

import pytest

from app.decision_intelligence.decision_rules import (
    DecisionInvariantViolation,
    DecisionPlanBoundaryError,
    DecisionTransitionError,
    apply_decision_transition,
    assert_can_produce_plan,
    can_produce_plan,
    compute_actionable,
    enforce_actionable_flag,
)
from app.decision_intelligence.schemas import Decision, DecisionStatus


def _decision(**overrides) -> Decision:
    fields = dict(project_id="proj-1", title="Launch pricing page", statement="Ship it")
    fields.update(overrides)
    return Decision(**fields)


# --- Construction ------------------------------------------------------


def test_decision_defaults_to_proposed_and_not_actionable():
    decision = _decision()
    assert decision.status == DecisionStatus.PROPOSED
    assert decision.actionable is False
    assert decision.comparison_ready is False
    assert decision.confidence == 0.5


def test_decision_id_and_created_at_are_auto_populated_and_unique():
    a, b = _decision(), _decision()
    assert a.id and b.id and a.id != b.id
    assert a.created_at is not None


# --- actionable cannot be self-asserted ---------------------------------


def test_llm_set_actionable_flag_is_ignored_when_status_not_ready():
    decision = _decision(status=DecisionStatus.PROPOSED, comparison_ready=True, actionable=True)
    assert compute_actionable(decision) is False


def test_llm_set_actionable_flag_is_ignored_when_comparison_not_ready():
    decision = _decision(status=DecisionStatus.READY_FOR_ACTION, comparison_ready=False, actionable=True)
    assert compute_actionable(decision) is False


def test_actionable_true_only_when_ready_and_comparison_ready():
    decision = _decision(status=DecisionStatus.READY_FOR_ACTION, comparison_ready=True, actionable=False)
    assert compute_actionable(decision) is True


def test_enforce_actionable_flag_overwrites_incorrect_llm_claim():
    decision = _decision(status=DecisionStatus.PROPOSED, comparison_ready=False, actionable=True)
    corrected = enforce_actionable_flag(decision)
    assert corrected.actionable is False
    assert decision.actionable is True  # original object is untouched


# --- Decision state machine --------------------------------------------


def test_decision_cannot_become_ready_for_action_when_comparison_not_ready():
    decision = _decision(status=DecisionStatus.PROPOSED, comparison_ready=False)
    with pytest.raises(DecisionInvariantViolation):
        apply_decision_transition(decision, DecisionStatus.READY_FOR_ACTION)


def test_decision_becomes_ready_for_action_when_comparison_ready():
    decision = _decision(status=DecisionStatus.PROPOSED, comparison_ready=True)
    updated = apply_decision_transition(decision, DecisionStatus.READY_FOR_ACTION)
    assert updated.status == DecisionStatus.READY_FOR_ACTION
    assert decision.status == DecisionStatus.PROPOSED  # original untouched


def test_decision_invalid_transition_raises_typed_error():
    decision = _decision(status=DecisionStatus.REJECTED)
    with pytest.raises(DecisionTransitionError) as exc_info:
        apply_decision_transition(decision, DecisionStatus.APPROVED)
    assert exc_info.value.current == DecisionStatus.REJECTED
    assert exc_info.value.target == DecisionStatus.APPROVED


def test_decision_full_approval_chain():
    decision = _decision(status=DecisionStatus.PROPOSED, comparison_ready=True)
    decision = apply_decision_transition(decision, DecisionStatus.READY_FOR_ACTION)
    decision = apply_decision_transition(decision, DecisionStatus.APPROVAL_REQUIRED)
    decision = apply_decision_transition(decision, DecisionStatus.APPROVED)
    assert decision.status == DecisionStatus.APPROVED


def test_decision_terminal_states_accept_no_further_transitions():
    for terminal in (DecisionStatus.REJECTED, DecisionStatus.SUPERSEDED):
        decision = _decision(status=terminal)
        with pytest.raises(DecisionTransitionError):
            apply_decision_transition(decision, DecisionStatus.PROPOSED)


# --- Decision -> ActionPlan boundary -------------------------------------


def test_boundary_blocks_insufficient_evidence():
    decision = _decision(status=DecisionStatus.INSUFFICIENT_EVIDENCE, comparison_ready=True)
    with pytest.raises(DecisionPlanBoundaryError):
        assert_can_produce_plan(decision)


def test_boundary_blocks_comparison_not_ready():
    decision = _decision(status=DecisionStatus.READY_FOR_ACTION, comparison_ready=False)
    with pytest.raises(DecisionPlanBoundaryError):
        assert_can_produce_plan(decision)


@pytest.mark.parametrize("status", [DecisionStatus.REJECTED, DecisionStatus.SUPERSEDED])
def test_boundary_blocks_rejected_and_superseded(status):
    decision = _decision(status=status, comparison_ready=True)
    with pytest.raises(DecisionPlanBoundaryError):
        assert_can_produce_plan(decision)


def test_boundary_allows_ready_and_comparison_ready_decision():
    decision = _decision(status=DecisionStatus.READY_FOR_ACTION, comparison_ready=True)
    assert_can_produce_plan(decision)  # must not raise
    assert can_produce_plan(decision) is True


def test_can_produce_plan_wrapper_returns_false_instead_of_raising():
    decision = _decision(status=DecisionStatus.INSUFFICIENT_EVIDENCE, comparison_ready=True)
    assert can_produce_plan(decision) is False
