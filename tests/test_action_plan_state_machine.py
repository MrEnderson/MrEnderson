"""Explicit ActionPlan state machine (v0.1.3.6, spec section 12). Illegal
transitions must fail closed with a typed error."""
from __future__ import annotations

import pytest

from app.decision_intelligence.action_plan_state_machine import (
    ActionPlanTransitionError,
    assert_transition,
    can_transition,
)
from app.decision_intelligence.schemas import ActionPlanStatus


def test_draft_to_validating_is_legal():
    assert_transition(ActionPlanStatus.DRAFT, ActionPlanStatus.VALIDATING)


def test_validating_to_ready_is_legal():
    assert_transition(ActionPlanStatus.VALIDATING, ActionPlanStatus.READY)


def test_ready_to_executing_is_legal():
    assert_transition(ActionPlanStatus.READY, ActionPlanStatus.EXECUTING)


def test_executing_to_all_downstream_states_legal():
    for target in (
        ActionPlanStatus.WAITING_FOR_APPROVAL, ActionPlanStatus.PARTIALLY_COMPLETED,
        ActionPlanStatus.COMPLETED, ActionPlanStatus.FAILED, ActionPlanStatus.CANCELLED,
    ):
        assert can_transition(ActionPlanStatus.EXECUTING, target) is True


def test_waiting_for_approval_can_return_to_executing():
    assert_transition(ActionPlanStatus.WAITING_FOR_APPROVAL, ActionPlanStatus.EXECUTING)


def test_partially_completed_can_return_to_executing():
    assert_transition(ActionPlanStatus.PARTIALLY_COMPLETED, ActionPlanStatus.EXECUTING)


def test_partially_completed_can_reach_completed():
    assert_transition(ActionPlanStatus.PARTIALLY_COMPLETED, ActionPlanStatus.COMPLETED)


# --- Illegal transitions (spec section 12's explicit examples) --------------


def test_completed_to_executing_is_illegal():
    assert can_transition(ActionPlanStatus.COMPLETED, ActionPlanStatus.EXECUTING) is False
    with pytest.raises(ActionPlanTransitionError):
        assert_transition(ActionPlanStatus.COMPLETED, ActionPlanStatus.EXECUTING)


def test_failed_to_completed_is_illegal():
    assert can_transition(ActionPlanStatus.FAILED, ActionPlanStatus.COMPLETED) is False
    with pytest.raises(ActionPlanTransitionError):
        assert_transition(ActionPlanStatus.FAILED, ActionPlanStatus.COMPLETED)


def test_draft_to_completed_is_illegal():
    assert can_transition(ActionPlanStatus.DRAFT, ActionPlanStatus.COMPLETED) is False
    with pytest.raises(ActionPlanTransitionError):
        assert_transition(ActionPlanStatus.DRAFT, ActionPlanStatus.COMPLETED)


def test_ready_to_waiting_for_approval_is_illegal_must_go_through_executing():
    assert can_transition(ActionPlanStatus.READY, ActionPlanStatus.WAITING_FOR_APPROVAL) is False


def test_waiting_for_approval_to_completed_is_illegal_direct():
    # Must go through EXECUTING first — see action_plan_orchestrator.py's
    # explicit re-entry-through-EXECUTING design.
    assert can_transition(ActionPlanStatus.WAITING_FOR_APPROVAL, ActionPlanStatus.COMPLETED) is False


def test_terminal_states_have_no_outgoing_transitions():
    for terminal in (ActionPlanStatus.COMPLETED, ActionPlanStatus.FAILED, ActionPlanStatus.CANCELLED):
        for target in ActionPlanStatus:
            if target == terminal:
                continue
            assert can_transition(terminal, target) is False


def test_action_plan_status_enum_matches_documented_set():
    assert {m.value for m in ActionPlanStatus} == {
        "DRAFT", "VALIDATING", "READY", "WAITING_FOR_APPROVAL", "EXECUTING",
        "PARTIALLY_COMPLETED", "COMPLETED", "FAILED", "CANCELLED",
    }
